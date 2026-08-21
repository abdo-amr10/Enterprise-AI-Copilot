"""Assign stable object IDs to individual Semantic Layer objects."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4


class SemanticLayerIdentityService:
    """Assign stable IDs to semantic objects within a Semantic Layer.

    semantic_layer_id and revision_id are NOT handled here — that
    responsibility belongs exclusively to SemanticLayerMetadataService.
    This service only fills in a missing `object_id` on individual
    entities, relationships, measures, dimensions, and business rules,
    so each object has a stable identity independent of its position
    or name (used for tracking across Incremental updates).
    """

    _SECTIONS = (
        "entities",
        "relationships",
        "measures",
        "dimensions",
        "business_rules",
    )

    def assign_object_ids(
        self,
        layer: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a copy of layer with object_id filled in where missing."""

        result = deepcopy(layer)

        for section in self._SECTIONS:
            items = result.get(section, [])
            if not isinstance(items, list):
                raise ValueError(
                    f"Semantic Layer section '{section}' must be a list."
                )

            for item in items:
                if not isinstance(item, dict):
                    raise ValueError(
                        f"Objects in '{section}' must be dictionaries."
                    )

                if item.get("object_id"):
                    continue

                name = item.get("name")
                if not isinstance(name, str) or not name.strip():
                    raise ValueError(
                        f"{section} objects require a name for identity assignment."
                    )

                item["object_id"] = f"obj-{uuid4()}"

        return result
