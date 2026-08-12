"""Validation engine for the generated semantic layer."""
from __future__ import annotations

from collections import Counter
from typing import Any


class SemanticLayerValidator:
    """Validate a semantic draft against the authoritative database schema."""

    def validate(self, draft: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        checks: dict[str, str] = {}

        self._check_required_sections(draft, errors)
        checks["structure"] = "passed" if not errors else "failed"

        tables = schema.get("tables", {})
        relationships = schema.get("relationships", [])
        self._check_relationships(draft.get("relationships", []), tables, relationships, errors)
        checks["relationships"] = "passed" if not self._has_type(errors, "relationship") else "failed"

        self._check_duplicates(draft, errors)
        checks["duplicates"] = "passed" if not self._has_type(errors, "duplicate") else "failed"

        self._check_entities(draft.get("entities", []), tables, warnings, errors)
        self._check_dimensions(draft.get("dimensions", []), tables, warnings, errors)
        self._check_measures(draft.get("measures", []), tables, warnings, errors)
        self._check_business_rules(draft.get("business_rules", []), warnings)
        checks["schema_consistency"] = "passed" if not any(
            issue["category"] in {"schema", "relationship", "mapping"} for issue in errors
        ) else "failed"

        if not draft.get("metadata", {}).get("human_review_required", True):
            warnings.append(self._warning("review", "Human review flag is disabled on the draft."))

        status = "failed" if errors else ("needs_review" if warnings else "passed")
        return {
            "status": status,
            "errors": errors,
            "warnings": warnings,
            "checks": checks,
            "summary": {
                "entities_checked": len(draft.get("entities", [])),
                "relationships_checked": len(draft.get("relationships", [])),
                "measures_checked": len(draft.get("measures", [])),
                "dimensions_checked": len(draft.get("dimensions", [])),
                "business_rules_checked": len(draft.get("business_rules", [])),
                "error_count": len(errors),
                "warning_count": len(warnings),
            },
        }

    @staticmethod
    def _check_required_sections(draft: dict[str, Any], errors: list[dict[str, Any]]) -> None:
        for section in ("metadata", "entities", "relationships", "measures", "dimensions", "business_rules"):
            if section not in draft:
                errors.append({"category": "structure", "code": "missing_section", "message": f"Missing section: {section}"})

    @staticmethod
    def _check_relationships(items: list[dict[str, Any]], tables: dict[str, Any], schema_relationships: list[dict[str, Any]], errors: list[dict[str, Any]]) -> None:
        known = {item.get("name"): item for item in schema_relationships}
        for item in items:
            name = item.get("name")
            if name not in known:
                errors.append({"category": "relationship", "code": "unknown_relationship", "message": f"Relationship '{name}' is not present in the source schema."})
                continue
            for side in ("from", "to"):
                table_key = f"{side}_table"
                column_key = f"{side}_column"
                table = item.get(table_key)
                column = item.get(column_key)
                if table not in tables:
                    errors.append({"category": "relationship", "code": "unknown_table", "message": f"{name}: unknown table '{table}'."})
                elif column not in {c.get("name") for c in tables[table].get("columns", [])}:
                    errors.append({"category": "relationship", "code": "unknown_column", "message": f"{name}: unknown column '{table}.{column}'."})

    @staticmethod
    def _check_duplicates(draft: dict[str, Any], errors: list[dict[str, Any]]) -> None:
        for section in ("entities", "relationships", "measures", "dimensions", "business_rules"):
            names = [item.get("name") for item in draft.get(section, [])]
            for name, count in Counter(names).items():
                if name and count > 1:
                    errors.append({"category": "duplicate", "code": "duplicate_name", "message": f"Duplicate {section[:-1]} name: '{name}'."})

    @staticmethod
    def _check_entities(items: list[dict[str, Any]], tables: dict[str, Any], warnings: list[dict[str, Any]], errors: list[dict[str, Any]]) -> None:
        for item in items:
            name = item.get("name")
            mapping = item.get("mapping") or item.get("table")
            if mapping and mapping not in tables:
                errors.append({"category": "schema", "code": "unknown_entity_table", "message": f"Entity '{name}' maps to unknown table '{mapping}'."})
            if not mapping:
                warnings.append(SemanticLayerValidator._warning("mapping", f"Entity '{name}' has no explicit table mapping."))

    @staticmethod
    def _check_dimensions(items: list[dict[str, Any]], tables: dict[str, Any], warnings: list[dict[str, Any]], errors: list[dict[str, Any]]) -> None:
        for item in items:
            mapping = item.get("mapping")
            if not mapping:
                warnings.append(SemanticLayerValidator._warning("mapping", f"Dimension '{item.get('name')}' has no explicit column mapping."))
                continue
            if "." not in mapping:
                errors.append({"category": "mapping", "code": "invalid_dimension_mapping", "message": f"Dimension '{item.get('name')}' mapping must be table.column: '{mapping}'."})
                continue
            table, column = mapping.split(".", 1)
            if table not in tables or column not in {c.get("name") for c in tables[table].get("columns", [])}:
                errors.append({"category": "mapping", "code": "unknown_dimension_mapping", "message": f"Dimension '{item.get('name')}' maps to unknown column '{mapping}'."})

    @staticmethod
    def _check_measures(items: list[dict[str, Any]], tables: dict[str, Any], warnings: list[dict[str, Any]], errors: list[dict[str, Any]]) -> None:
        for item in items:
            mapping = item.get("mapping")
            if not mapping:
                warnings.append(SemanticLayerValidator._warning("mapping", f"Measure '{item.get('name')}' has no explicit mapping."))
                continue
            if "." not in mapping:
                errors.append({"category": "mapping", "code": "invalid_measure_mapping", "message": f"Measure '{item.get('name')}' mapping must be table.column: '{mapping}'."})
                continue
            table, column = mapping.split(".", 1)
            if table not in tables or column not in {c.get("name") for c in tables[table].get("columns", [])}:
                errors.append({"category": "mapping", "code": "unknown_measure_mapping", "message": f"Measure '{item.get('name')}' maps to unknown column '{mapping}'."})

    @staticmethod
    def _check_business_rules(items: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
        for item in items:
            if not item.get("description"):
                warnings.append(SemanticLayerValidator._warning("documentation", f"Business rule '{item.get('name')}' has no description."))

    @staticmethod
    def _warning(code: str, message: str) -> dict[str, Any]:
        return {"category": "warning", "code": code, "message": message}

    @staticmethod
    def _has_type(errors: list[dict[str, Any]], category: str) -> bool:
        return any(item.get("category") == category for item in errors)
