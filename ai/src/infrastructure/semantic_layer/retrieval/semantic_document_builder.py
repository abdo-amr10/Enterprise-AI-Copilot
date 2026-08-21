"""Deterministically render semantic objects as retrieval-oriented documents."""

from __future__ import annotations

from hashlib import sha256
from typing import Any


class SemanticDocumentBuilder:
    _SECTIONS = (
        ("entity", "entities"), ("relationship", "relationships"),
        ("measure", "measures"), ("dimension", "dimensions"),
        ("business_rule", "business_rules"),
    )

    def build(self, layer: dict[str, Any]) -> list[dict[str, Any]]:
        metadata = layer.get("metadata", {})
        semantic_layer_id, revision_id = metadata.get("semantic_layer_id"), metadata.get("revision_id")
        if not semantic_layer_id or not revision_id:
            raise ValueError("Approved Semantic Layer requires semantic_layer_id and revision_id.")
        documents: list[dict[str, Any]] = []
        for object_type, section in self._SECTIONS:
            for item in layer.get(section, []):
                if not isinstance(item, dict):
                    raise ValueError(f"Semantic Layer section '{section}' must contain dictionaries.")
                object_id = item.get("object_id") or self._fallback_object_id(object_type, item)
                documents.append({
                    "id": f"{semantic_layer_id}:{revision_id}:{object_type}:{object_id}",
                    "object_id": object_id, "object_type": object_type,
                    "text": self._render(object_type, item), "payload": item,
                    "semantic_layer_id": semantic_layer_id, "revision_id": revision_id,
                })
        return documents

    @staticmethod
    def _fallback_object_id(object_type: str, item: dict[str, Any]) -> str:
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Semantic {object_type} requires object_id or name.")
        return f"derived-{sha256(f'{object_type}:{name}'.encode()).hexdigest()[:16]}"

    @staticmethod
    def _render(object_type: str, item: dict[str, Any]) -> str:
        labels = {
            "entity": ("Entity", ("name", "description", "aliases", "attributes", "business_meaning", "mapping")),
            "relationship": ("Relationship", ("name", "description", "from_table", "from_column", "to_table", "to_column", "cardinality", "relationship_type", "business_meaning")),
            "measure": ("Measure", ("name", "description", "calculation", "formula", "aggregation", "dimensions", "mapping")),
            "dimension": ("Dimension", ("name", "description", "business_meaning", "mapping", "aliases")),
            "business_rule": ("Business rule", ("name", "description", "conditions", "business_meaning")),
        }
        title, fields = labels[object_type]
        values = [f"{field.replace('_', ' ')}: {item[field]}" for field in fields if item.get(field) not in (None, "", [], {})]
        return "\n".join([title, *values])
