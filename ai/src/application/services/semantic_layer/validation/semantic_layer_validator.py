"""Validation engine for generated Semantic Layer drafts."""

from __future__ import annotations

from collections import Counter
from typing import Any


class SemanticLayerValidator:
    """Validate a Semantic Layer draft against authoritative source metadata."""

    REQUIRED_SECTIONS = (
        "metadata",
        "entities",
        "relationships",
        "measures",
        "dimensions",
        "business_rules",
    )

    def validate(
        self,
        draft: dict[str, Any],
        schema: dict[str, Any],
        relationships: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Validate a Semantic Layer draft.

        Args:
            draft: Semantic Layer draft to validate.
            schema: Authoritative normalized database schema.

        Returns:
            Structured validation result containing status, errors,
            warnings, checks, and summary.
        """

        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        checks: dict[str, str] = {}

        self._check_required_sections(draft, errors)
        self._check_metadata(draft, errors)

        checks["structure"] = (
            "passed" if not self._has_category(errors, "structure")
            else "failed"
        )

        tables = schema.get("tables", {})
        if not isinstance(tables, dict):
            errors.append(
                {
                    "category": "schema",
                    "code": "invalid_schema_tables",
                    "message": "Authoritative schema.tables must be an object.",
                }
            )
            tables = {}
        if not isinstance(relationships, list):
            errors.append(
                {
                    "category": "relationship",
                    "code": "invalid_relationships",
                    "message": "Authoritative relationships must be a list.",
                }
            )
            relationships = []

        metadata = draft.get("metadata", {}) if isinstance(draft, dict) else {}
        trigger_type = metadata.get("trigger_type") if isinstance(metadata, dict) else None

        self._check_relationships(
            draft.get("relationships", []),
            tables,
            relationships,
            errors,
            require_all_source_relationships=trigger_type == "FullRebuild",
        )

        checks["relationships"] = (
            "passed"
            if not self._has_category(errors, "relationship")
            else "failed"
        )

        self._check_duplicates(draft, errors)

        checks["duplicates"] = (
            "passed"
            if not self._has_category(errors, "duplicate")
            else "failed"
        )

        self._check_entities(
            draft.get("entities", []),
            tables,
            warnings,
            errors,
        )

        self._check_dimensions(
            draft.get("dimensions", []),
            tables,
            warnings,
            errors,
        )

        self._check_measures(
            draft.get("measures", []),
            tables,
            warnings,
            errors,
        )

        self._check_business_rules(
            draft.get("business_rules", []),
            warnings,
        )

        self._check_validation_issues(
            draft.get("validation_issues", []),
            warnings,
        )

        checks["schema_consistency"] = (
            "passed"
            if not any(
                error.get("category")
                in {"schema", "relationship", "mapping"}
                for error in errors
            )
            else "failed"
        )

        status = "failed" if errors else "passed"

        return {
            "status": status,
            "errors": errors,
            "warnings": warnings,
            "checks": checks,
            "summary": {
                "entities_checked": len(
                    draft.get("entities", [])
                ),
                "relationships_checked": len(
                    draft.get("relationships", [])
                ),
                "measures_checked": len(
                    draft.get("measures", [])
                ),
                "dimensions_checked": len(
                    draft.get("dimensions", [])
                ),
                "business_rules_checked": len(
                    draft.get("business_rules", [])
                ),
                "error_count": len(errors),
                "warning_count": len(warnings),
            },
        }

    @classmethod
    def _check_required_sections(
        cls,
        draft: dict[str, Any],
        errors: list[dict[str, Any]],
    ) -> None:
        """Ensure all required Semantic Layer sections exist."""

        if not isinstance(draft, dict):
            errors.append(
                {
                    "category": "structure",
                    "code": "invalid_draft",
                    "message": "Semantic Layer draft must be a dictionary.",
                }
            )
            return

        for section in cls.REQUIRED_SECTIONS:
            if section not in draft:
                errors.append(
                    {
                        "category": "structure",
                        "code": "missing_section",
                        "message": f"Missing section: '{section}'.",
                    }
                )

    @staticmethod
    def _check_relationships(
        items: list[dict[str, Any]],
        tables: dict[str, Any],
        authoritative_relationships: list[dict[str, Any]],
        errors: list[dict[str, Any]],
        require_all_source_relationships: bool,
    ) -> None:
        """Validate relationships against authoritative schema metadata."""

        known = {
            item.get("name"): item
            for item in authoritative_relationships
            if item.get("name")
        }

        draft_names: set[str] = set()

        for item in items:
            name = item.get("name")

            if not name:
                errors.append(
                    {
                        "category": "relationship",
                        "code": "missing_relationship_name",
                        "message": "Relationship is missing a name.",
                    }
                )
                continue

            draft_names.add(name)

            if name not in known:
                errors.append(
                    {
                        "category": "relationship",
                        "code": "unknown_relationship",
                        "message": (
                            f"Relationship '{name}' is not present "
                            "in the source schema."
                        ),
                    }
                )
                continue

            source = known[name]

            for field in (
                "from_table",
                "from_column",
                "to_table",
                "to_column",
                "cardinality",
                "relationship_type",
            ):
                expected = source.get(field)
                actual = item.get(field)

                if actual != expected:
                    errors.append(
                        {
                            "category": "relationship",
                            "code": "relationship_mismatch",
                            "message": (
                                f"Relationship '{name}' has an invalid "
                                f"'{field}'. Expected '{expected}', "
                                f"got '{actual}'."
                            ),
                        }
                    )

            for side in ("from", "to"):
                table_name = item.get(f"{side}_table")
                column_name = item.get(f"{side}_column")

                if table_name not in tables:
                    errors.append(
                        {
                            "category": "relationship",
                            "code": "unknown_table",
                            "message": (
                                f"{name}: unknown table "
                                f"'{table_name}'."
                            ),
                        }
                    )
                    continue

                columns = {
                    column.get("name")
                    for column in tables[table_name].get(
                        "columns",
                        [],
                    )
                }

                if column_name not in columns:
                    errors.append(
                        {
                            "category": "relationship",
                            "code": "unknown_column",
                            "message": (
                                f"{name}: unknown column "
                                f"'{table_name}.{column_name}'."
                            ),
                        }
                    )

        if require_all_source_relationships:
            missing_relationships = set(known) - draft_names
            for name in sorted(missing_relationships):
                errors.append(
                    {
                        "category": "relationship",
                        "code": "missing_relationship",
                        "message": (
                            f"Required relationship '{name}' is missing "
                            "from the Semantic Layer."
                        ),
                    }
                )

    @staticmethod
    def _check_duplicates(
        draft: dict[str, Any],
        errors: list[dict[str, Any]],
    ) -> None:
        """Detect duplicate semantic object names within each section."""

        sections = (
            "entities",
            "relationships",
            "measures",
            "dimensions",
            "business_rules",
        )

        for section in sections:
            names = [
                item.get("name")
                for item in draft.get(section, [])
                if isinstance(item, dict)
            ]

            for name, count in Counter(names).items():
                if name and count > 1:
                    errors.append(
                        {
                            "category": "duplicate",
                            "code": "duplicate_name",
                            "message": (
                                f"Duplicate {section[:-1]} name: "
                                f"'{name}'."
                            ),
                        }
                    )

    @staticmethod
    def _check_entities(
        items: list[dict[str, Any]],
        tables: dict[str, Any],
        warnings: list[dict[str, Any]],
        errors: list[dict[str, Any]],
    ) -> None:
        """Validate entity-to-table mappings."""

        for item in items:
            name = item.get("name")
            mapping = item.get("mapping") or item.get("table")

            if mapping and mapping not in tables:
                errors.append(
                    {
                        "category": "schema",
                        "code": "unknown_entity_table",
                        "message": (
                            f"Entity '{name}' maps to unknown "
                            f"table '{mapping}'."
                        ),
                    }
                )

            if not mapping:
                errors.append({
                    "category": "mapping",
                    "code": "missing_entity_mapping",
                    "message": f"Entity '{name}' requires a physical table mapping.",
                })

    @staticmethod
    def _check_dimensions(
        items: list[dict[str, Any]],
        tables: dict[str, Any],
        warnings: list[dict[str, Any]],
        errors: list[dict[str, Any]],
    ) -> None:
        """Validate dimension mappings against source columns."""

        for item in items:
            name = item.get("name")
            mapping = item.get("mapping")

            if not mapping:
                errors.append({
                    "category": "mapping",
                    "code": "missing_dimension_mapping",
                    "message": f"Dimension '{name}' requires a physical table.column mapping.",
                })
                continue

            table, column = SemanticLayerValidator._split_mapping(
                mapping,
                name,
                "dimension",
                errors,
            )

            if table is None:
                continue

            if not SemanticLayerValidator._column_exists(
                table,
                column,
                tables,
            ):
                errors.append(
                    {
                        "category": "mapping",
                        "code": "unknown_dimension_mapping",
                        "message": (
                            f"Dimension '{name}' maps to unknown "
                            f"column '{mapping}'."
                        ),
                    }
                )

    @staticmethod
    def _check_measures(
        items: list[dict[str, Any]],
        tables: dict[str, Any],
        warnings: list[dict[str, Any]],
        errors: list[dict[str, Any]],
    ) -> None:
        """Validate measure mappings against source columns."""

        for item in items:
            name = item.get("name")
            mapping = item.get("mapping")

            if not mapping:
                errors.append({
                    "category": "mapping",
                    "code": "missing_measure_mapping",
                    "message": f"Measure '{name}' requires a physical table.column mapping.",
                })
                continue

            table, column = SemanticLayerValidator._split_mapping(
                mapping,
                name,
                "measure",
                errors,
            )

            if table is None:
                continue

            if not SemanticLayerValidator._column_exists(
                table,
                column,
                tables,
            ):
                errors.append(
                    {
                        "category": "mapping",
                        "code": "unknown_measure_mapping",
                        "message": (
                            f"Measure '{name}' maps to unknown "
                            f"column '{mapping}'."
                        ),
                    }
                )

    @staticmethod
    def _split_mapping(
        mapping: str,
        name: str | None,
        element_type: str,
        errors: list[dict[str, Any]],
    ) -> tuple[str | None, str | None]:
        """Split a semantic mapping into table and column."""

        if "." not in mapping:
            errors.append(
                {
                    "category": "mapping",
                    "code": f"invalid_{element_type}_mapping",
                    "message": (
                        f"{element_type.capitalize()} '{name}' mapping "
                        f"must use table.column format: '{mapping}'."
                    ),
                }
            )
            return None, None

        return mapping.split(".", 1)

    @staticmethod
    def _column_exists(
        table: str,
        column: str,
        tables: dict[str, Any],
    ) -> bool:
        """Check whether a column exists in a source table."""

        if table not in tables:
            return False

        return column in {
            item.get("name")
            for item in tables[table].get("columns", [])
        }

    @staticmethod
    def _check_business_rules(
        items: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> None:
        """Check business-rule descriptions."""

        for item in items:
            if not item.get("description"):
                warnings.append(
                    SemanticLayerValidator._warning(
                        "documentation",
                        (
                            f"Business rule '{item.get('name')}' "
                            "has no description."
                        ),
                    )
                )

    @staticmethod
    def _check_validation_issues(
        issues: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> None:
        """Report unresolved issues generated during semantic construction."""

        for issue in issues:
            if not isinstance(issue, dict):
                continue

            message = issue.get("message")

            if message:
                warnings.append(
                    {
                        "category": "validation_issue",
                        "code": "unresolved_validation_issue",
                        "message": message,
                    }
                )

    @staticmethod
    def _warning(
        code: str,
        message: str,
    ) -> dict[str, Any]:
        """Create a standardized validation warning."""

        return {
            "category": "warning",
            "code": code,
            "message": message,
        }

    @staticmethod
    def _has_category(
        errors: list[dict[str, Any]],
        category: str,
    ) -> bool:
        """Check whether errors contain a specific category."""

        return any(
            error.get("category") == category
            for error in errors
        )

    @staticmethod
    def _check_metadata(
        draft: dict[str, Any],
        errors: list[dict[str, Any]],
    ) -> None:
        """Validate required Semantic Layer revision metadata."""

        metadata = draft.get("metadata")

        if not isinstance(metadata, dict):
            errors.append(
                {
                    "category": "structure",
                    "code": "missing_metadata",
                    "message": "Semantic Layer metadata is required.",
                }
            )
            return

        required_fields = (
            "semantic_layer_id",
            "revision_id",
            "status",
        )

        for field in required_fields:
            value = metadata.get(field)

            if not isinstance(value, str) or not value.strip():
                errors.append(
                    {
                        "category": "metadata",
                        "code": "missing_metadata_field",
                        "message": (
                            f"Metadata field '{field}' is required."
                        ),
                    }
                )
