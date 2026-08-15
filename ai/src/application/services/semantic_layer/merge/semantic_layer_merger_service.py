"""Application service for merging incremental semantic-layer changes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


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
                AffectedObject.to_dict(): object_id, section, name,
                action ("upsert" or "delete").

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

        affected_by_section = self._group_affected_objects(
            affected_objects,
        )

        for section in self._MERGEABLE_SECTIONS:
            changes = incremental_layer.get(section, [])

            if not isinstance(changes, list):
                raise ValueError(
                    f"Incremental section '{section}' must be a list."
                )

            self._merge_section(
                merged_layer=merged_layer,
                changes=changes,
                affected_objects=affected_by_section.get(section, {}),
                section=section,
            )

        return merged_layer

    @classmethod
    def _merge_section(
        cls,
        merged_layer: dict[str, Any],
        changes: list[dict[str, Any]],
        affected_objects: dict[str, str],
        section: str,
    ) -> None:
        """Apply affected incremental changes to one semantic section."""

        existing_items = merged_layer.setdefault(section, [])

        if not isinstance(existing_items, list):
            raise ValueError(
                f"Approved section '{section}' must be a list."
            )

        existing_by_name = {
            item.get("name"): index
            for index, item in enumerate(existing_items)
            if isinstance(item, dict) and item.get("name")
        }

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

            # Ignore anything that was not explicitly marked as affected.
            if name not in affected_objects:
                continue

            action = affected_objects[name]

            if action == "delete":
                cls._delete_item(
                    existing_items=existing_items,
                    existing_by_name=existing_by_name,
                    name=name,
                    section=section,
                )
                continue

            if action == "upsert":
                cls._upsert_item(
                    existing_items=existing_items,
                    existing_by_name=existing_by_name,
                    change=change,
                    name=name,
                )

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
        affected_objects: list[dict[str, Any]],
    ) -> dict[str, dict[str, str]]:
        """Group affected objects by semantic-layer section."""

        grouped: dict[str, dict[str, str]] = {}

        for item in affected_objects:
            section = item["section"]
            name = item["name"]
            action = item.get("action", "upsert")

            grouped.setdefault(section, {})[name] = action

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
            name = item.get("name")
            action = item.get("action", "upsert")

            if section not in cls._MERGEABLE_SECTIONS:
                raise ValueError(
                    f"Unsupported affected-object section: '{section}'."
                )

            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    "Affected object name cannot be empty."
                )

            if action not in {"upsert", "delete"}:
                raise ValueError(
                    "Affected object action must be 'upsert' or 'delete'."
                )

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
