"""Application service for merging incremental semantic-layer changes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
import re


class SemanticLayerMergeService:
    """Merge incremental changes into the approved Semantic Layer.

    The approved Semantic Layer is always used as the base. Only
    explicitly affected semantic objects may be added, replaced, or
    removed — anything in the incremental layer that isn't listed in
    affected_objects is ignored, so the LLM cannot silently change
    something it wasn't asked to touch.

    This service is responsible ONLY for structural merging. It does
    not assign semantic_layer_id/revision_id/status (that is
    SemanticLayerMetadataService's job, applied by the Generation
    Pipeline right after merge()) and it does not perform validation,
    auto-fixing, human review, embedding, indexing, or persistence.
    """

    _MERGEABLE_SECTIONS = (
        "entities",
        "relationships",
        "measures",
        "dimensions",
        "business_rules",
    )

    def merge(
        self,
        approved_layer: dict[str, Any],
        incremental_layer: dict[str, Any],
        affected_objects: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Merge incremental changes into the approved Semantic Layer.

        Args:
            approved_layer:
                Previously approved Semantic Layer used as the base.

            incremental_layer:
                Newly generated incremental Semantic Layer containing
                changes for affected objects.

            affected_objects:
                Explicit list of semantic objects affected by the
                incremental generation. Each dict matches
                AffectedObject.to_dict(): section and id. The id must
                identify an object in the approved base revision.

        Returns:
            A new Semantic Layer dict containing the approved base
            combined with the incremental changes. It has NO identity
            metadata yet — the caller is expected to pass this through
            SemanticLayerMetadataService.create_revision() next.

        Raises:
            ValueError:
                If the input layers or affected objects are invalid.
        """

        self._validate_layer(
            approved_layer,
            "approved_layer",
        )

        self._validate_layer(
            incremental_layer,
            "incremental_layer",
        )

        self._validate_affected_objects(
            affected_objects,
        )

        merged_layer = deepcopy(approved_layer)

        affected_by_section = self._group_affected_objects(approved_layer, affected_objects)

        for section in self._MERGEABLE_SECTIONS:
            changes = incremental_layer.get(section, [])

            if not isinstance(changes, list):
                raise ValueError(
                    f"Incremental section '{section}' must be a list."
                )

            self._merge_section(
                merged_layer=merged_layer,
                changes=changes,
                affected_objects=affected_by_section.get(section, []),
                section=section,
            )

        return merged_layer

    @classmethod
    def _merge_section(
        cls,
        merged_layer: dict[str, Any],
        changes: list[dict[str, Any]],
        affected_objects: list[dict[str, str]],
        section: str,
    ) -> None:
        """Apply affected incremental changes to one semantic section."""

        existing_items = merged_layer.setdefault(section, [])

        if not isinstance(existing_items, list):
            raise ValueError(
                f"Approved section '{section}' must be a list."
            )

        existing_by_id = {
            item.get("object_id"): index
            for index, item in enumerate(existing_items)
            if isinstance(item, dict) and item.get("object_id")
        }
        additions = {item["name"]: item for item in affected_objects if item["action"] == "add"}
        updates = {item["id"]: item for item in affected_objects if item["action"] == "update"}
        deletions = {item["id"] for item in affected_objects if item["action"] == "delete"}

        for object_id in deletions:
            if object_id not in existing_by_id:
                raise ValueError(f"Cannot delete unknown {section} '{object_id}'.")
        existing_items[:] = [item for item in existing_items if item.get("object_id") not in deletions]

        for change in changes:
            if not isinstance(change, dict):
                raise ValueError(
                    f"Items in '{section}' must be dictionaries."
                )

            name = change.get("name")

            if not name:
                raise ValueError(
                    f"Incremental {section} item must contain a name."
                )

            object_id = change.get("object_id")
            if object_id in updates:
                index = existing_by_id.get(object_id)
                if index is None:
                    raise ValueError(f"Cannot update unknown {section} '{object_id}'.")
                existing_items[index] = deepcopy(change)
            elif name in additions:
                if any(item.get("name") == name for item in existing_items):
                    raise ValueError(f"Cannot add duplicate {section} '{name}'.")
                slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
                kind = "entity" if section == "entities" else section[:-1]
                expected_id = additions[name].get("id") or change.get("object_id") or f"obj-{kind}-{slug}"
                new_item = deepcopy(change)
                new_item["object_id"] = expected_id
                existing_items.append(new_item)

    @staticmethod
    def _upsert_item(
        existing_items: list[dict[str, Any]],
        existing_by_name: dict[str, int],
        change: dict[str, Any],
        name: str,
    ) -> None:
        """Add a new semantic object or replace an existing one."""

        if name in existing_by_name:
            index = existing_by_name[name]
            existing_items[index] = deepcopy(change)
        else:
            existing_items.append(deepcopy(change))

    @staticmethod
    def _delete_item(
        existing_items: list[dict[str, Any]],
        existing_by_name: dict[str, int],
        name: str,
        section: str,
    ) -> None:
        """Remove an affected semantic object when it exists."""

        if name not in existing_by_name:
            raise ValueError(
                f"Cannot delete unknown {section} '{name}'."
            )

        index = existing_by_name[name]
        existing_items.pop(index)

    @classmethod
    def _group_affected_objects(
        cls,
        approved_layer: dict[str, Any],
        affected_objects: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, str]]]:
        """Validate operations against stable IDs and group them by section."""

        grouped: dict[str, list[dict[str, str]]] = {}

        for item in affected_objects:
            section = item["section"]
            action = item["action"]
            object_id = item.get("id")
            if action in {"update", "delete"} and not any(
                isinstance(object_, dict) and object_.get("object_id") == object_id
                for object_ in approved_layer.get(section, [])
            ):
                raise ValueError(f"Affected object '{object_id}' was not found in {section}.")
            grouped.setdefault(section, []).append(item)

        return grouped

    @classmethod
    def _validate_affected_objects(
        cls,
        affected_objects: list[dict[str, Any]],
    ) -> None:
        """Validate the affected-object contract."""

        if not isinstance(affected_objects, list):
            raise ValueError(
                "affected_objects must be a list."
            )

        if not affected_objects:
            raise ValueError(
                "affected_objects cannot be empty for Incremental generation."
            )

        for item in affected_objects:
            if not isinstance(item, dict):
                raise ValueError(
                    "Each affected object must be a dictionary."
                )

            section = item.get("section")
            object_id = item.get("id")
            action = item.get("action")

            if section not in cls._MERGEABLE_SECTIONS:
                raise ValueError(
                    f"Unsupported affected-object section: '{section}'."
                )

            if action not in {"add", "update", "delete"}:
                raise ValueError("Affected object action must be add, update, or delete.")
            if action in {"update", "delete"} and (not isinstance(object_id, str) or not object_id.strip()):
                raise ValueError("Affected object id is required for update and delete.")
            if action == "add" and not isinstance(item.get("name"), str):
                raise ValueError("Affected object name is required for add.")

    @staticmethod
    def _validate_layer(
        layer: dict[str, Any],
        name: str,
    ) -> None:
        """Validate a Semantic Layer object."""

        if not isinstance(layer, dict):
            raise ValueError(
                f"{name} must be a dictionary."
            )

        if "metadata" not in layer:
            raise ValueError(
                f"{name} must contain a metadata section."
            )

        for section in SemanticLayerMergeService._MERGEABLE_SECTIONS:
            if section in layer and not isinstance(layer[section], list):
                raise ValueError(
                    f"{name} section '{section}' must be a list."
                )
