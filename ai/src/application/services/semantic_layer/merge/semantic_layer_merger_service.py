"""Structural merge service for authorized incremental semantic-layer patches."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class SemanticLayerMergeService:
    """Merge an incremental patch into an approved baseline.

    This service is the authorization boundary for incremental changes. It
    performs structural merging only; it never validates semantics or assigns
    permanent object identities.
    """

    _MERGEABLE_SECTIONS = (
        "entities", "relationships", "measures", "dimensions", "business_rules", "security_domains"
    )

    def merge(
        self,
        approved_layer: dict[str, Any],
        incremental_layer: dict[str, Any],
        affected_objects: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self._validate_layer(approved_layer, "approved_layer")
        self._validate_layer(incremental_layer, "incremental_layer")
        self._validate_affected_objects(affected_objects)
        affected_by_section = self._group_affected_objects(
            approved_layer, affected_objects
        )
        merged_layer = deepcopy(approved_layer)
        for section in self._MERGEABLE_SECTIONS:
            self._merge_section(
                merged_layer, incremental_layer.get(section, []),
                affected_by_section.get(section, []), section,
            )
        self._cascade_deleted_entities(
            approved_layer, affected_by_section.get("entities", []), merged_layer
        )
        return merged_layer

    @classmethod
    def _merge_section(
        cls,
        merged_layer: dict[str, Any],
        changes: list[dict[str, Any]],
        affected_objects: list[dict[str, Any]],
        section: str,
    ) -> None:
        existing_items = merged_layer.setdefault(section, [])
        if not isinstance(existing_items, list):
            raise ValueError(f"Approved section '{section}' must be a list.")
        if not isinstance(changes, list):
            raise ValueError(f"Incremental section '{section}' must be a list.")

        additions = {
            item["name"]: item for item in affected_objects if item["action"] == "add"
        }
        updates = {
            item["id"]: item for item in affected_objects if item["action"] == "update"
        }
        deletions = {
            item["id"] for item in affected_objects if item["action"] == "delete"
        }
        existing_ids = {
            item.get("object_id") for item in existing_items if isinstance(item, dict)
        }
        for object_id in deletions:
            if object_id not in existing_ids:
                raise ValueError(f"Cannot delete unknown {section} '{object_id}'.")

        existing_items[:] = [
            item for item in existing_items
            if isinstance(item, dict) and item.get("object_id") not in deletions
        ]
        # Deletions alter positions, so updates must use a fresh index.
        existing_by_id = {
            item.get("object_id"): index
            for index, item in enumerate(existing_items)
            if isinstance(item, dict) and item.get("object_id")
        }
        existing_ids_by_name = {
            item.get("name"): item.get("object_id")
            for item in existing_items
            if isinstance(item, dict) and item.get("name") and item.get("object_id")
        }

        for change in changes:
            if not isinstance(change, dict):
                raise ValueError(f"Items in '{section}' must be dictionaries.")
            # Some builders return a complete section instead of a sparse patch.
            # A Backend-authorized deletion wins over an echoed copy of that
            # object. Only the exact authorized ID is ignored; all other
            # changes still have to pass the affected_objects check.
            if change.get("object_id") in deletions:
                continue
            name = change.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Incremental {section} item must contain a name.")
            # Builders may return an identity-free patch. Resolve such an
            # update only through the Backend-authorized affected-object ID;
            # never infer a target outside that scope.
            object_id = change.get("object_id") or existing_ids_by_name.get(name)

            if object_id in updates:
                index = existing_by_id.get(object_id)
                if index is None:
                    raise ValueError(f"Cannot update unknown {section} '{object_id}'.")
                if section == "security_domains":
                    existing_domain = existing_items[index]
                    updated_domain = deepcopy(existing_domain)
                    for field in (
                        "name",
                        "canonical_root",
                        "canonical_predicate",
                        "security_parameter",
                        "security_scope",
                        "description",
                    ):
                        if field in change and change[field]:
                            updated_domain[field] = change[field]

                    existing_paths = existing_domain.get("propagation_paths", [])
                    new_paths = change.get("propagation_paths", [])
                    if isinstance(new_paths, list):
                        path_by_target = {
                            p.get("target_table").lower(): p
                            for p in existing_paths
                            if isinstance(p, dict) and p.get("target_table")
                        }
                        for np in new_paths:
                            if isinstance(np, dict) and np.get("target_table"):
                                path_by_target[np.get("target_table").lower()] = deepcopy(np)
                        updated_domain["propagation_paths"] = list(path_by_target.values())

                    updated_domain["object_id"] = object_id
                    existing_items[index] = updated_domain
                else:
                    updated_item = deepcopy(change)
                    updated_item["object_id"] = object_id
                    existing_items[index] = updated_item
                continue

            if name in additions:
                if any(
                    item.get("name") == name
                    for item in existing_items if isinstance(item, dict)
                ):
                    raise ValueError(f"Cannot add duplicate {section} '{name}'.")
                new_item = deepcopy(change)
                # New-object identity belongs exclusively to IdentityService.
                new_item.pop("object_id", None)
                existing_items.append(new_item)
                continue

            raise ValueError(
                f"Incremental change for '{section}' is outside "
                "the affected_objects scope."
            )

    @classmethod
    def _group_affected_objects(
        cls, approved_layer: dict[str, Any], affected_objects: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in affected_objects:
            section, action = item["section"], item["action"]
            existing_items = approved_layer.get(section, [])
            if action in {"update", "delete"} and not any(
                isinstance(existing, dict) and existing.get("object_id") == item["id"]
                for existing in existing_items
            ):
                raise ValueError(
                    f"Affected object '{item['id']}' was not found "
                    f"in approved section '{section}'."
                )
            if action == "add" and any(
                isinstance(existing, dict) and existing.get("name") == item["name"]
                for existing in existing_items
            ):
                raise ValueError(f"Cannot add existing {section} '{item['name']}'.")
            grouped.setdefault(section, []).append(item)
        return grouped

    @classmethod
    def _validate_affected_objects(cls, affected_objects: list[dict[str, Any]]) -> None:
        if not isinstance(affected_objects, list) or not affected_objects:
            raise ValueError("affected_objects cannot be empty for Incremental merge.")
        seen: set[tuple[str, str, str | None, str | None]] = set()
        for item in affected_objects:
            if not isinstance(item, dict):
                raise ValueError("Each affected object must be a dictionary.")
            section, action = item.get("section"), item.get("action")
            object_id, name = item.get("id"), item.get("name")
            if section not in cls._MERGEABLE_SECTIONS:
                raise ValueError(f"Unsupported affected-object section: '{section}'.")
            if action not in {"add", "update", "delete"}:
                raise ValueError("Affected object action must be add, update, or delete.")
            if action in {"update", "delete"} and (
                not isinstance(object_id, str) or not object_id.strip()
            ):
                raise ValueError("Affected object id is required for update and delete.")
            if action == "add" and (
                not isinstance(name, str) or not name.strip() or object_id is not None
            ):
                raise ValueError("Affected object add requires a name and no id.")
            key = (section, action, object_id, name)
            if key in seen:
                raise ValueError(f"Duplicate affected-object operation: {key}.")
            seen.add(key)

    @classmethod
    def _validate_layer(cls, layer: dict[str, Any], name: str) -> None:
        if not isinstance(layer, dict):
            raise ValueError(f"{name} must be a dictionary.")
        if "metadata" not in layer:
            raise ValueError(f"{name} must contain a metadata section.")
        for section in cls._MERGEABLE_SECTIONS:
            if section in layer and not isinstance(layer[section], list):
                raise ValueError(f"{name} section '{section}' must be a list.")
            for item in layer.get(section, []):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"{name} section '{section}' must contain only dictionaries."
                    )

    @classmethod
    def _cascade_deleted_entities(
        cls,
        approved_layer: dict[str, Any],
        affected_entities: list[dict[str, Any]],
        merged_layer: dict[str, Any],
    ) -> None:
        deleted_entity_ids = {
            item["id"] for item in affected_entities if item.get("action") == "delete"
        }
        if not deleted_entity_ids:
            return

        deleted_tables: set[str] = set()
        for entity in approved_layer.get("entities", []):
            if isinstance(entity, dict) and entity.get("object_id") in deleted_entity_ids:
                if entity.get("mapping"):
                    deleted_tables.add(entity["mapping"])
                if entity.get("name"):
                    deleted_tables.add(entity["name"])

        if not deleted_tables:
            return

        # Cascade from relationships
        if "relationships" in merged_layer and isinstance(merged_layer["relationships"], list):
            merged_layer["relationships"][:] = [
                rel for rel in merged_layer["relationships"]
                if isinstance(rel, dict)
                and rel.get("from_table") not in deleted_tables
                and rel.get("to_table") not in deleted_tables
            ]

        # Cascade from dimensions
        if "dimensions" in merged_layer and isinstance(merged_layer["dimensions"], list):
            merged_layer["dimensions"][:] = [
                dim for dim in merged_layer["dimensions"]
                if isinstance(dim, dict)
                and not any(
                    isinstance(dim.get("mapping"), str) and (
                        dim["mapping"].startswith(f"{tbl}.") or dim["mapping"] == tbl
                    )
                    for tbl in deleted_tables
                )
            ]

        # Cascade from measures
        if "measures" in merged_layer and isinstance(merged_layer["measures"], list):
            merged_layer["measures"][:] = [
                m for m in merged_layer["measures"]
                if isinstance(m, dict)
                and m.get("source_table") not in deleted_tables
                and not any(
                    isinstance(m.get("mapping"), str) and (
                        m["mapping"].startswith(f"{tbl}.") or m["mapping"] == tbl
                    )
                    for tbl in deleted_tables
                )
            ]
