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
        has_semantic_context: bool = False,
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
        self._check_entity_coverage(
            draft.get("entities", []),
            tables,
            errors,
            require_all_source_tables=trigger_type == "FullRebuild",
        )

        self._check_dimensions(
            draft.get("dimensions", []),
            tables,
            warnings,
            errors,
        )
        self._check_dimension_coverage(
            draft.get("dimensions", []),
            tables,
            errors,
            require_all_source_columns=trigger_type == "FullRebuild",
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
        self._check_security_domains(
            draft.get("security_domains", []),
            tables,
            warnings,
            errors,
        )
        self._check_required_semantic_sections(
            draft,
            errors,
            require_complete_baseline=(
                trigger_type == "FullRebuild" and has_semantic_context
            ),
        )

        self._check_validation_issues(
            draft.get("validation_issues", []),
            warnings,
        )

        checks["security_domains"] = (
            "passed"
            if not self._has_category(errors, "security_domain")
            else "failed"
        )

        checks["schema_consistency"] = (
            "passed"
            if not any(
                error.get("category")
                in {"schema", "relationship", "mapping", "security_domain"}
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
                "security_domains_checked": len(
                    draft.get("security_domains", [])
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

                if expected is not None and actual != expected:
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

            cardinality = item.get("cardinality")
            valid_cardinalities = {
                "1:1", "1:N", "N:1", "N:N",
                "one_to_one", "one_to_many", "many_to_one", "many_to_many",
                "unknown",
            }
            if cardinality is not None and cardinality not in valid_cardinalities:
                errors.append(
                    {
                        "category": "relationship",
                        "code": "invalid_cardinality",
                        "message": (
                            f"Relationship '{name}' has invalid cardinality '{cardinality}'. "
                            f"Must be one of: {sorted(valid_cardinalities)}."
                        ),
                    }
                )

            sec_prop = item.get("security_propagation")
            valid_sec_prop = {"allowed", "not_allowed", "conditional", "unknown"}
            if sec_prop is not None and sec_prop not in valid_sec_prop:
                errors.append(
                    {
                        "category": "relationship",
                        "code": "invalid_security_propagation",
                        "message": (
                            f"Relationship '{name}' has invalid security_propagation '{sec_prop}'. "
                            f"Must be one of: {sorted(valid_sec_prop)}."
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
            "security_domains",
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
    def _check_entity_coverage(
        items: list[dict[str, Any]],
        tables: dict[str, Any],
        errors: list[dict[str, Any]],
        require_all_source_tables: bool,
    ) -> None:
        """Require Full Rebuilds to represent every source table as an entity."""

        if not require_all_source_tables:
            return

        represented_tables = {
            item.get("mapping") or item.get("table")
            for item in items
            if isinstance(item, dict)
        }
        for table_name in sorted(set(tables) - represented_tables):
            errors.append(
                {
                    "category": "coverage",
                    "code": "missing_entity_mapping",
                    "message": (
                        "FullRebuild must include an entity for source "
                        f"table '{table_name}'."
                    ),
                }
            )

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
    def _check_dimension_coverage(
        items: list[dict[str, Any]],
        tables: dict[str, Any],
        errors: list[dict[str, Any]],
        require_all_source_columns: bool,
    ) -> None:
        """Require a Full Rebuild to expose every physical source column.

        Validating only the mappings that happen to be present lets a model
        return a structurally-valid but incomplete Semantic Layer.  A full
        rebuild is expected to create the complete queryable baseline, while
        an incremental draft is intentionally allowed to contain only changes.
        """

        if not require_all_source_columns:
            return

        represented_mappings = {
            item.get("mapping")
            for item in items
            if isinstance(item, dict) and isinstance(item.get("mapping"), str)
        }
        expected_mappings = {
            f"{table_name}.{column.get('name')}"
            for table_name, table in tables.items()
            if isinstance(table, dict)
            for column in table.get("columns", [])
            if isinstance(column, dict) and column.get("name")
        }

        for mapping in sorted(expected_mappings - represented_mappings):
            errors.append(
                {
                    "category": "coverage",
                    "code": "missing_dimension_mapping",
                    "message": (
                        "FullRebuild must include a dimension for source "
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

            distinct_key = item.get("distinct_key")
            if distinct_key and not SemanticLayerValidator._column_exists(table, distinct_key, tables):
                errors.append(
                    {
                        "category": "mapping",
                        "code": "unknown_distinct_key",
                        "message": (
                            f"Measure '{name}' specifies unknown distinct_key "
                            f"'{table}.{distinct_key}'."
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
    def _check_security_domains(
        items: list[dict[str, Any]],
        tables: dict[str, Any],
        warnings: list[dict[str, Any]],
        errors: list[dict[str, Any]],
    ) -> None:
        """Validate security domain declarations, canonical roots, and propagation paths."""
        if not isinstance(items, list):
            errors.append(
                {
                    "category": "security_domain",
                    "code": "invalid_security_domains_section",
                    "message": "security_domains must be a list of domain objects.",
                }
            )
            return

        valid_propagations = {"allowed", "not_allowed", "conditional", "unknown"}

        for item in items:
            if not isinstance(item, dict):
                errors.append(
                    {
                        "category": "security_domain",
                        "code": "invalid_security_domain",
                        "message": "Each security domain must be an object.",
                    }
                )
                continue

            name = item.get("name")
            if not name or not isinstance(name, str) or not name.strip():
                errors.append(
                    {
                        "category": "security_domain",
                        "code": "missing_security_domain_name",
                        "message": "Security domain is missing a required name.",
                    }
                )

            canonical_root = item.get("canonical_root")
            if not canonical_root or not isinstance(canonical_root, str) or not canonical_root.strip():
                errors.append(
                    {
                        "category": "security_domain",
                        "code": "missing_canonical_root",
                        "message": f"Security domain '{name or 'unnamed'}' requires a canonical_root (table.column format).",
                    }
                )
            else:
                if "." in canonical_root:
                    root_table, root_col = canonical_root.split(".", 1)
                    if root_table not in tables:
                        errors.append(
                            {
                                "category": "security_domain",
                                "code": "unknown_canonical_root_table",
                                "message": f"Security domain '{name}' canonical root table '{root_table}' not in schema.",
                            }
                        )
                    elif not SemanticLayerValidator._column_exists(root_table, root_col, tables):
                        errors.append(
                            {
                                "category": "security_domain",
                                "code": "unknown_canonical_root_column",
                                "message": f"Security domain '{name}' canonical root column '{root_col}' not in table '{root_table}'.",
                            }
                        )

            canonical_predicate = item.get("canonical_predicate")
            if not canonical_predicate or not isinstance(canonical_predicate, str) or not canonical_predicate.strip():
                errors.append(
                    {
                        "category": "security_domain",
                        "code": "missing_canonical_predicate",
                        "message": f"Security domain '{name or 'unnamed'}' requires a canonical_predicate string.",
                    }
                )

            propagation_paths = item.get("propagation_paths")
            if propagation_paths is not None:
                if not isinstance(propagation_paths, list):
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "invalid_propagation_paths",
                            "message": f"Security domain '{name}' propagation_paths must be a list.",
                        }
                    )
                else:
                    for path_item in propagation_paths:
                        if not isinstance(path_item, dict):
                            errors.append(
                                {
                                    "category": "security_domain",
                                    "code": "invalid_propagation_path",
                                    "message": f"Security domain '{name}' propagation path must be an object.",
                                }
                            )
                            continue
                        target_table = path_item.get("target_table")
                        if not target_table or not isinstance(target_table, str):
                            errors.append(
                                {
                                    "category": "security_domain",
                                    "code": "missing_target_table",
                                    "message": f"Security domain '{name}' propagation path is missing target_table.",
                                }
                            )
                        elif target_table not in tables:
                            errors.append(
                                {
                                    "category": "security_domain",
                                    "code": "unknown_target_table",
                                    "message": f"Security domain '{name}' propagation path target_table '{target_table}' not in schema.",
                                }
                            )

                        path_str = path_item.get("path")
                        if not path_str or not isinstance(path_str, str):
                            errors.append(
                                {
                                    "category": "security_domain",
                                    "code": "missing_path_expression",
                                    "message": f"Security domain '{name}' propagation path for '{target_table}' is missing path expression.",
                                }
                            )

                        prop = path_item.get("propagation")
                        if prop is not None and prop not in valid_propagations:
                            errors.append(
                                {
                                    "category": "security_domain",
                                    "code": "invalid_propagation_value",
                                    "message": f"Security domain '{name}' propagation path has invalid propagation '{prop}'. Must be one of: {sorted(valid_propagations)}.",
                                }
                            )

                        pred_eq = path_item.get("predicate_equivalence")
                        if pred_eq is not None and not isinstance(pred_eq, (dict, bool, str)):
                            errors.append(
                                {
                                    "category": "security_domain",
                                    "code": "invalid_predicate_equivalence",
                                    "message": f"Security domain '{name}' predicate_equivalence must be a dictionary or boolean/string.",
                                }
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

    @staticmethod
    def _check_required_semantic_sections(
        draft: dict[str, Any],
        errors: list[dict[str, Any]],
        require_complete_baseline: bool,
    ) -> None:
        """Prevent empty semantic enrichment sections from being approved.

        A Full Rebuild with documentation or a business glossary establishes
        a reusable semantic baseline, so it must include enrichment.  With
        schema-only input, enrichment is optional and is left for human
        review rather than forcing the model to invent business meaning.
        Incremental drafts may legitimately leave either section unchanged.
        """

        if not require_complete_baseline:
            return

        for section in ("measures", "business_rules"):
            if not draft.get(section):
                errors.append(
                    {
                        "category": "coverage",
                        "code": f"missing_{section}",
                        "message": (
                            "FullRebuild must include at least one "
                            f"{section[:-1].replace('_', ' ')}."
                        ),
                    }
                )
