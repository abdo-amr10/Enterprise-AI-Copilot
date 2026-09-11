"""Deterministically render semantic objects as retrieval-oriented documents."""

from __future__ import annotations

from hashlib import sha256
from typing import Any


class SemanticDocumentBuilder:
    _SECTIONS = (
        ("entity", "entities"),
        ("relationship", "relationships"),
        ("measure", "measures"),
        ("dimension", "dimensions"),
        ("business_rule", "business_rules"),
        ("security_domain", "security_domains"),
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
                    "object_id": object_id,
                    "object_type": object_type,
                    "type": object_type,
                    "text": self._render(object_type, item),
                    "payload": item,
                    "semantic_layer_id": semantic_layer_id,
                    "revision_id": revision_id,
                })
        return documents

    @staticmethod
    def _fallback_object_id(object_type: str, item: dict[str, Any]) -> str:
        name = item.get("name") or item.get("canonical_root") or item.get("mapping")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Semantic {object_type} requires object_id or name.")
        return f"derived-{sha256(f'{object_type}:{name}'.encode()).hexdigest()[:16]}"

    @classmethod
    def _render(cls, object_type: str, item: dict[str, Any]) -> str:
        labels: dict[str, tuple[str, tuple[str, ...]]] = {
            "entity": (
                "Entity",
                (
                    "name", "description", "mapping", "source_table", "grain",
                    "natural_grain", "grain_key", "primary_identifier", "primary_key",
                    "security_domain", "security_scope", "aliases", "attributes",
                    "business_meaning", "business_definition",
                ),
            ),
            "relationship": (
                "Relationship",
                (
                    "name", "description", "from_table", "from_column",
                    "to_table", "to_column", "source_table", "source_column",
                    "target_table", "target_column", "cardinality",
                    "relationship_type", "nullable", "join_direction",
                    "allowed_join_types", "aggregation_behavior", "fanout_risk",
                    "security_propagation", "predicate_equivalence",
                    "security_domain", "business_meaning",
                ),
            ),
            "measure": (
                "Measure",
                (
                    "name", "description", "mapping", "source_table",
                    "source_column", "natural_grain", "natural_entity",
                    "aggregation", "aggregation_function", "distinct_required",
                    "distinct_key", "null_behavior", "filter_dependencies",
                    "fanout_sensitive", "business_definition", "calculation",
                    "formula", "dimensions",
                ),
            ),
            "dimension": (
                "Dimension",
                (
                    "name", "description", "mapping", "grain", "natural_grain",
                    "data_type", "type", "business_meaning", "aliases",
                ),
            ),
            "business_rule": (
                "Business rule",
                (
                    "name", "description", "security_domain",
                    "canonical_predicate", "canonical_root", "rule_type",
                    "fanout_risk", "requires_preaggregation", "distinct_required",
                    "distinct_key", "conditions", "business_meaning",
                ),
            ),
            "security_domain": (
                "Security domain",
                (
                    "name", "canonical_root", "canonical_predicate",
                    "security_scope", "description", "propagation_paths",
                ),
            ),
        }
        title, fields = labels.get(object_type, (object_type.capitalize(), tuple(item.keys())))
        values = []
        for field in fields:
            val = item.get(field)
            if val in (None, "", [], {}):
                continue
            if isinstance(val, (list, set, tuple)):
                formatted_val = ", ".join(str(v) for v in val)
            elif isinstance(val, dict):
                formatted_val = ", ".join(f"{k}: {v}" for k, v in val.items())
            else:
                formatted_val = str(val)
            values.append(f"{field.replace('_', ' ')}: {formatted_val}")
        return "\n".join([title, *values])
