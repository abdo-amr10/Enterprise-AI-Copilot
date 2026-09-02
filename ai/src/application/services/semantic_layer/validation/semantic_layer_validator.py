"""Validation engine for generated Semantic Layer drafts."""

from __future__ import annotations

from collections import Counter
import re
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
        security_rules: list[dict[str, Any]] | None = None,
        authoritative_security_rules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Validate a Semantic Layer draft against authoritative metadata.

        Args:
            draft: Semantic Layer draft.
            schema: Authoritative normalized database schema.
            relationships: Authoritative relationship metadata.
            has_semantic_context: Whether semantic enrichment sources were
                available during generation.
            security_rules: Optional authoritative normalized RLS/security
                metadata extracted from Documentation or another trusted
                semantic source.
            authoritative_security_rules: Explicit authoritative normalized
                RLS/security metadata (aliases/takes precedence over security_rules).

        Returns:
            Structured validation result containing status, errors,
            warnings, checks, and summary.
        """

        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        checks: dict[str, str] = {}

        if not isinstance(draft, dict):
            errors.append(
                {
                    "category": "structure",
                    "code": "invalid_draft",
                    "message": "Semantic Layer draft must be a dictionary.",
                }
            )
            return self._build_result(
                draft={},
                errors=errors,
                warnings=warnings,
                checks=checks,
            )

        self._check_required_sections(draft, errors)
        self._check_metadata(draft, errors)

        checks["structure"] = (
            "passed"
            if not self._has_category(errors, "structure")
            else "failed"
        )

        tables = schema.get("tables", {}) if isinstance(schema, dict) else {}

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

        metadata = draft.get("metadata", {})
        trigger_type = (
            metadata.get("trigger_type")
            if isinstance(metadata, dict)
            else None
        )

        draft_relationships = draft.get("relationships", [])
        if not isinstance(draft_relationships, list):
            errors.append(
                {
                    "category": "relationship",
                    "code": "invalid_draft_relationships",
                    "message": "Semantic Layer relationships must be a list.",
                }
            )
            draft_relationships = []

        self._check_relationships(
            draft_relationships,
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

        entities = draft.get("entities", [])
        dimensions = draft.get("dimensions", [])
        measures = draft.get("measures", [])
        business_rules = draft.get("business_rules", [])
        security_domains = draft.get("security_domains", [])

        if not isinstance(entities, list):
            errors.append(
                {
                    "category": "structure",
                    "code": "invalid_entities_section",
                    "message": "entities must be a list.",
                }
            )
            entities = []

        if not isinstance(dimensions, list):
            errors.append(
                {
                    "category": "structure",
                    "code": "invalid_dimensions_section",
                    "message": "dimensions must be a list.",
                }
            )
            dimensions = []

        if not isinstance(measures, list):
            errors.append(
                {
                    "category": "structure",
                    "code": "invalid_measures_section",
                    "message": "measures must be a list.",
                }
            )
            measures = []

        if not isinstance(business_rules, list):
            errors.append(
                {
                    "category": "structure",
                    "code": "invalid_business_rules_section",
                    "message": "business_rules must be a list.",
                }
            )
            business_rules = []

        effective_rules = (
            authoritative_security_rules
            if authoritative_security_rules is not None
            else security_rules
        )

        self._check_entities(
            entities,
            tables,
            warnings,
            errors,
            security_domains=security_domains,
        )

        self._check_entity_coverage(
            entities,
            tables,
            errors,
            require_all_source_tables=trigger_type == "FullRebuild",
        )

        self._check_dimensions(
            dimensions,
            tables,
            warnings,
            errors,
        )

        self._check_dimension_coverage(
            dimensions,
            tables,
            errors,
            require_all_source_columns=trigger_type == "FullRebuild",
        )

        self._check_measures(
            measures,
            tables,
            warnings,
            errors,
        )

        self._check_business_rules(
            business_rules,
            warnings,
        )

        self._check_security_domains(
            security_domains,
            tables,
            warnings,
            errors,
            relationships=relationships,
        )

        if effective_rules is not None:
            self._check_security_rule_coverage(
                security_domains,
                effective_rules,
                errors,
                require_all_rules=trigger_type == "FullRebuild",
                tables=tables,
                relationships=relationships,
            )

        self._check_required_semantic_sections(
            draft,
            errors,
            require_complete_baseline=(
                trigger_type == "FullRebuild"
                and has_semantic_context
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
                in {
                    "schema",
                    "relationship",
                    "mapping",
                    "security_domain",
                }
                for error in errors
            )
            else "failed"
        )

        return self._build_result(
            draft=draft,
            errors=errors,
            warnings=warnings,
            checks=checks,
        )

    @classmethod
    def _build_result(
        cls,
        draft: dict[str, Any],
        errors: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        checks: dict[str, str],
    ) -> dict[str, Any]:
        """Build the final validation result."""

        return {
            "status": "failed" if errors else "passed",
            "errors": errors,
            "warnings": warnings,
            "checks": checks,
            "summary": {
                "entities_checked": len(draft.get("entities", [])),
                "relationships_checked": len(
                    draft.get("relationships", [])
                ),
                "measures_checked": len(draft.get("measures", [])),
                "dimensions_checked": len(draft.get("dimensions", [])),
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
        """Validate relationships against authoritative metadata."""

        known = {
            item.get("name"): item
            for item in authoritative_relationships
            if isinstance(item, dict) and item.get("name")
        }

        draft_names: set[str] = set()

        for item in items:
            if not isinstance(item, dict):
                errors.append(
                    {
                        "category": "relationship",
                        "code": "invalid_relationship",
                        "message": "Each relationship must be an object.",
                    }
                )
                continue

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
                            "in the authoritative relationship metadata."
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
                "1:1",
                "1:N",
                "N:1",
                "N:N",
                "one_to_one",
                "one_to_many",
                "many_to_one",
                "many_to_many",
                "unknown",
            }

            if (
                cardinality is not None
                and cardinality not in valid_cardinalities
            ):
                errors.append(
                    {
                        "category": "relationship",
                        "code": "invalid_cardinality",
                        "message": (
                            f"Relationship '{name}' has invalid "
                            f"cardinality '{cardinality}'."
                        ),
                    }
                )

            sec_prop = item.get("security_propagation")

            valid_sec_prop = {
                "allowed",
                "not_allowed",
                "conditional",
                "unknown",
            }

            if sec_prop is not None and sec_prop not in valid_sec_prop:
                errors.append(
                    {
                        "category": "relationship",
                        "code": "invalid_security_propagation",
                        "message": (
                            f"Relationship '{name}' has invalid "
                            f"security_propagation '{sec_prop}'."
                        ),
                    }
                )

            status = item.get("status")

            valid_statuses = {
                "PROVIDED",
                "INFERRED",
                "UNCERTAIN",
                "NO_SUPPORTED_RELATIONSHIP",
                "METADATA_UNAVAILABLE",
                "provided",
                "inferred",
                "uncertain",
            }

            if status is not None and status not in valid_statuses:
                errors.append(
                    {
                        "category": "relationship",
                        "code": "invalid_relationship_status",
                        "message": (
                            f"Relationship '{name}' has invalid "
                            f"status '{status}'."
                        ),
                    }
                )

            confidence = item.get("confidence")

            if confidence is not None:
                if (
                    not isinstance(confidence, (int, float))
                    or isinstance(confidence, bool)
                    or not 0.0 <= float(confidence) <= 1.0
                ):
                    errors.append(
                        {
                            "category": "relationship",
                            "code": "invalid_confidence",
                            "message": (
                                f"Relationship '{name}' has invalid "
                                f"confidence '{confidence}'."
                            ),
                        }
                    )

            for side in ("from", "to"):
                table_name = item.get(f"{side}_table")
                column_name = item.get(f"{side}_column")

                if (
                    not table_name
                    and isinstance(
                        item.get(
                            "source" if side == "from" else "target"
                        ),
                        dict,
                    )
                ):
                    endpoint = item.get(
                        "source" if side == "from" else "target",
                        {},
                    )
                    table_name = endpoint.get("table")
                    column_name = endpoint.get("column")

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
                    for column in tables[table_name].get("columns", [])
                    if isinstance(column, dict)
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
            items = draft.get(section, [])

            if not isinstance(items, list):
                continue

            names = [
                item.get("name")
                for item in items
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
        security_domains: list[dict[str, Any]] | None = None,
    ) -> None:
        """Validate entity-to-table mappings and security domain consistency."""

        for item in items:
            if not isinstance(item, dict):
                errors.append(
                    {
                        "category": "mapping",
                        "code": "invalid_entity",
                        "message": "Each entity must be an object.",
                    }
                )
                continue

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
                errors.append(
                    {
                        "category": "mapping",
                        "code": "missing_entity_mapping",
                        "message": (
                            f"Entity '{name}' requires a physical "
                            "table mapping."
                        ),
                    }
                )

            sec_domain = item.get("security_domain") or item.get("security_scope")
            if sec_domain and security_domains is not None:
                has_matching_domain = any(
                    isinstance(d, dict)
                    and (d.get("name") == sec_domain or d.get("security_scope") == sec_domain)
                    for d in security_domains
                )
                if not has_matching_domain:
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "security_domain_undefined",
                            "message": (
                                f"Entity '{name}' references security_domain '{sec_domain}', "
                                "but no matching security domain definition exists in security_domains."
                            ),
                        }
                    )

    @staticmethod
    def _check_entity_coverage(
        items: list[dict[str, Any]],
        tables: dict[str, Any],
        errors: list[dict[str, Any]],
        require_all_source_tables: bool,
    ) -> None:
        """Require Full Rebuilds to represent every source table."""

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
            if not isinstance(item, dict):
                errors.append(
                    {
                        "category": "mapping",
                        "code": "invalid_dimension",
                        "message": "Each dimension must be an object.",
                    }
                )
                continue

            name = item.get("name")
            mapping = item.get("mapping")

            if not mapping:
                errors.append(
                    {
                        "category": "mapping",
                        "code": "missing_dimension_mapping",
                        "message": (
                            f"Dimension '{name}' requires a physical "
                            "table.column mapping."
                        ),
                    }
                )
                continue

            table, column = SemanticLayerValidator._split_mapping(
                mapping,
                name,
                "dimension",
                errors,
            )

            if table is None or column is None:
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
        """Require Full Rebuild to expose every physical source column."""

        if not require_all_source_columns:
            return

        represented_mappings = {
            item.get("mapping")
            for item in items
            if (
                isinstance(item, dict)
                and isinstance(item.get("mapping"), str)
            )
        }

        expected_mappings = {
            f"{table_name}.{column.get('name')}"
            for table_name, table in tables.items()
            if isinstance(table, dict)
            for column in table.get("columns", [])
            if (
                isinstance(column, dict)
                and column.get("name")
            )
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
            if not isinstance(item, dict):
                errors.append(
                    {
                        "category": "mapping",
                        "code": "invalid_measure",
                        "message": "Each measure must be an object.",
                    }
                )
                continue

            name = item.get("name")
            mapping = item.get("mapping")

            if not mapping:
                errors.append(
                    {
                        "category": "mapping",
                        "code": "missing_measure_mapping",
                        "message": (
                            f"Measure '{name}' requires a physical "
                            "table.column mapping."
                        ),
                    }
                )
                continue

            table, column = SemanticLayerValidator._split_mapping(
                mapping,
                name,
                "measure",
                errors,
            )

            if table is None or column is None:
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

            if distinct_key and not SemanticLayerValidator._column_exists(
                table,
                distinct_key,
                tables,
            ):
                errors.append(
                    {
                        "category": "mapping",
                        "code": "unknown_distinct_key",
                        "message": (
                            f"Measure '{name}' specifies unknown "
                            f"distinct_key '{table}.{distinct_key}'."
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
                        "must use table.column format."
                    ),
                }
            )
            return None, None

        table, column = mapping.split(".", 1)

        if not table or not column:
            errors.append(
                {
                    "category": "mapping",
                    "code": f"invalid_{element_type}_mapping",
                    "message": (
                        f"{element_type.capitalize()} '{name}' mapping "
                        "must use table.column format."
                    ),
                }
            )
            return None, None

        return table, column

    @staticmethod
    def _column_exists(
        table: str,
        column: str,
        tables: dict[str, Any],
    ) -> bool:
        """Check whether a column exists in a source table."""

        if table not in tables:
            return False

        table_metadata = tables[table]

        if not isinstance(table_metadata, dict):
            return False

        return column in {
            item.get("name")
            for item in table_metadata.get("columns", [])
            if isinstance(item, dict)
        }

    @staticmethod
    def _check_business_rules(
        items: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> None:
        """Check business-rule descriptions."""

        for item in items:
            if not isinstance(item, dict):
                continue

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
        relationships: list[dict[str, Any]] | None = None,
    ) -> None:
        """Validate security domain structure, source mappings, and propagation relationships."""

        if not isinstance(items, list):
            errors.append(
                {
                    "category": "security_domain",
                    "code": "invalid_security_domains_section",
                    "message": (
                        "security_domains must be a list of domain objects."
                    ),
                }
            )
            return

        valid_propagations = {
            "allowed",
            "not_allowed",
            "conditional",
            "unknown",
        }

        for item in items:
            if not isinstance(item, dict):
                errors.append(
                    {
                        "category": "security_domain",
                        "code": "invalid_security_domain",
                        "message": (
                            "Each security domain must be an object."
                        ),
                    }
                )
                continue

            name = item.get("name")

            if not name or not isinstance(name, str) or not name.strip():
                errors.append(
                    {
                        "category": "security_domain",
                        "code": "missing_security_domain_name",
                        "message": (
                            "Security domain is missing a required name."
                        ),
                    }
                )

            canonical_root = item.get("canonical_root")

            if (
                not canonical_root
                or not isinstance(canonical_root, str)
                or not canonical_root.strip()
            ):
                errors.append(
                    {
                        "category": "security_domain",
                        "code": "missing_canonical_root",
                        "message": (
                            f"Security domain '{name or 'unnamed'}' "
                            "requires a canonical_root."
                        ),
                    }
                )
            elif "." not in canonical_root:
                errors.append(
                    {
                        "category": "security_domain",
                        "code": "invalid_canonical_root",
                        "message": (
                            f"Security domain '{name}' canonical_root "
                            "must use table.column format."
                        ),
                    }
                )
            else:
                root_table, root_col = canonical_root.split(".", 1)

                if root_table not in tables:
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "unknown_canonical_root_table",
                            "message": (
                                f"Security domain '{name}' canonical root "
                                f"table '{root_table}' not in schema."
                            ),
                        }
                    )
                elif not SemanticLayerValidator._column_exists(
                    root_table,
                    root_col,
                    tables,
                ):
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "unknown_canonical_root_column",
                            "message": (
                                f"Security domain '{name}' canonical root "
                                f"column '{root_col}' not in table "
                                f"'{root_table}'."
                            ),
                        }
                    )

            canonical_predicate = item.get("canonical_predicate")

            if (
                not canonical_predicate
                or not isinstance(canonical_predicate, str)
                or not canonical_predicate.strip()
            ):
                errors.append(
                    {
                        "category": "security_domain",
                        "code": "missing_canonical_predicate",
                        "message": (
                            f"Security domain '{name or 'unnamed'}' "
                            "requires a canonical_predicate string."
                        ),
                    }
                )

            propagation_paths = item.get("propagation_paths")

            if propagation_paths is None:
                continue

            if not isinstance(propagation_paths, list):
                errors.append(
                    {
                        "category": "security_domain",
                        "code": "invalid_propagation_paths",
                        "message": (
                            f"Security domain '{name}' "
                            "propagation_paths must be a list."
                        ),
                    }
                )
                continue

            for path_item in propagation_paths:
                if not isinstance(path_item, dict):
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "invalid_propagation_path",
                            "message": (
                                f"Security domain '{name}' propagation "
                                "path must be an object."
                            ),
                        }
                    )
                    continue

                target_table = path_item.get("target_table")

                if not target_table or not isinstance(target_table, str):
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "missing_target_table",
                            "message": (
                                f"Security domain '{name}' propagation "
                                "path is missing target_table."
                            ),
                        }
                    )
                elif target_table not in tables:
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "unknown_target_table",
                            "message": (
                                f"Security domain '{name}' propagation "
                                f"path target_table '{target_table}' "
                                "not in schema."
                            ),
                        }
                    )

                path_str = path_item.get("path")

                if not path_str or not isinstance(path_str, str):
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "missing_path_expression",
                            "message": (
                                f"Security domain '{name}' propagation "
                                f"path for '{target_table}' is missing "
                                "path expression."
                            ),
                        }
                    )
                else:
                    # Validate join relationships in propagation path
                    join_matches = re.findall(
                        r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)",
                        path_str,
                    )
                    for t1, c1, t2, c2 in join_matches:
                        t1_lower, t2_lower = t1.lower(), t2.lower()
                        if t1_lower not in tables or t2_lower not in tables:
                            missing_t = t1 if t1_lower not in tables else t2
                            errors.append(
                                {
                                    "category": "security_domain",
                                    "code": "unknown_target_table",
                                    "message": (
                                        f"Security propagation path references unknown table '{missing_t}'."
                                    ),
                                }
                            )
                            continue

                        if relationships:
                            matching_rel = None
                            for r in relationships:
                                if not isinstance(r, dict):
                                    continue
                                rf = (r.get("from_table") or r.get("source_table") or "").lower()
                                rt = (r.get("to_table") or r.get("target_table") or "").lower()
                                if (rf == t1_lower and rt == t2_lower) or (rf == t2_lower and rt == t1_lower):
                                    matching_rel = r
                                    break

                            if matching_rel is None:
                                errors.append(
                                    {
                                        "category": "security_domain",
                                        "code": "unsupported_security_propagation_path",
                                        "message": (
                                            f"Security propagation path for '{target_table}' references join "
                                            f"'{t1}.{c1} = {t2}.{c2}' not backed by authoritative relationships."
                                        ),
                                    }
                                )
                            elif (
                                matching_rel.get("confidence") == "UNCERTAIN"
                                or matching_rel.get("is_executable") is False
                                or matching_rel.get("authoritative") is False
                            ):
                                errors.append(
                                    {
                                        "category": "security_domain",
                                        "code": "unsupported_security_propagation_path",
                                        "message": (
                                            f"Security propagation path for '{target_table}' uses uncertain "
                                            f"or unexecutable relationship between '{t1}' and '{t2}'."
                                        ),
                                    }
                                )

                prop = path_item.get("propagation")

                if prop is not None and prop not in valid_propagations:
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "invalid_propagation_value",
                            "message": (
                                f"Security domain '{name}' propagation "
                                f"path has invalid propagation '{prop}'."
                            ),
                        }
                    )

                pred_eq = path_item.get("predicate_equivalence")

                if pred_eq is not None and not isinstance(
                    pred_eq,
                    (dict, bool, str),
                ):
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "invalid_predicate_equivalence",
                            "message": (
                                f"Security domain '{name}' "
                                "predicate_equivalence must be a "
                                "dictionary, boolean, or string."
                            ),
                        }
                    )

    @staticmethod
    def _check_security_rule_coverage(
        security_domains: list[dict[str, Any]],
        security_rules: list[dict[str, Any]],
        errors: list[dict[str, Any]],
        require_all_rules: bool,
        tables: dict[str, Any] | None = None,
        relationships: list[dict[str, Any]] | None = None,
    ) -> None:
        """Compare Semantic Layer security domains to authoritative RLS rules."""

        if not isinstance(security_rules, list):
            errors.append(
                {
                    "category": "security_domain",
                    "code": "invalid_authoritative_security_rules",
                    "message": (
                        "Authoritative security_rules must be a list."
                    ),
                }
            )
            return

        draft_by_name = {
            item.get("name"): item
            for item in security_domains
            if isinstance(item, dict) and item.get("name")
        }

        for rule in security_rules:
            if not isinstance(rule, dict):
                continue

            rule_name = rule.get("name") or rule.get("security_scope")

            if not rule_name:
                continue

            domain = draft_by_name.get(rule_name)

            if domain is None:
                if require_all_rules:
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "missing_authoritative_security_rule",
                            "message": (
                                f"Required authoritative security rule/domain '{rule_name}' "
                                "is missing from the Semantic Layer."
                            ),
                        }
                    )
                continue

            # 1. Canonical Root validation
            expected_root = rule.get("canonical_root")
            if expected_root is not None:
                actual_root = domain.get("canonical_root")
                if actual_root != expected_root:
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "canonical_root_mismatch",
                            "message": (
                                f"Security domain '{rule_name}' has an invalid canonical_root. "
                                f"Expected '{expected_root}', got '{actual_root}'."
                            ),
                        }
                    )

            # 2. Canonical Predicate validation
            expected_pred = rule.get("canonical_predicate")
            if expected_pred is not None:
                actual_pred = domain.get("canonical_predicate")
                if actual_pred != expected_pred:
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "canonical_predicate_mismatch",
                            "message": (
                                f"Security domain '{rule_name}' has an invalid canonical_predicate. "
                                f"Expected '{expected_pred}', got '{actual_pred}'."
                            ),
                        }
                    )

            # 3. Security Parameter validation
            expected_param = rule.get("security_parameter")
            if expected_param is not None:
                actual_param = domain.get("security_parameter")
                pred = domain.get("canonical_predicate") or ""
                if actual_param != expected_param or expected_param not in pred:
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "security_parameter_mismatch",
                            "message": (
                                f"Security domain '{rule_name}' has a security parameter mismatch. "
                                f"Expected '{expected_param}', got '{actual_param}'."
                            ),
                        }
                    )

            # 4. Target Table Coverage validation
            expected_paths = rule.get("propagation_paths")
            actual_paths = domain.get("propagation_paths") or []
            if isinstance(expected_paths, list):
                expected_targets = {
                    p.get("target_table").lower()
                    for p in expected_paths
                    if isinstance(p, dict) and p.get("target_table")
                }
                actual_targets = {
                    p.get("target_table").lower()
                    for p in actual_paths
                    if isinstance(p, dict) and p.get("target_table")
                }
                root_tbl = (expected_root or "").split(".", 1)[0].lower()
                if root_tbl and (domain.get("canonical_root") or "").lower().startswith(f"{root_tbl}."):
                    actual_targets.add(root_tbl)

                if require_all_rules:
                    missing_targets = expected_targets - actual_targets
                    for mt in sorted(missing_targets):
                        errors.append(
                            {
                                "category": "security_domain",
                                "code": "missing_security_target_coverage",
                                "message": (
                                    f"Authoritative RLS target table '{mt}' is missing from "
                                    f"propagation paths in security domain '{rule_name}'."
                                ),
                            }
                        )

                # 5. Invented target tables in propagation paths
                invented_targets = (actual_targets - expected_targets) - {root_tbl}
                for it in sorted(invented_targets):
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "invented_security_rule",
                            "message": (
                                f"Security domain '{rule_name}' contains invented security "
                                f"propagation path for target table '{it}'."
                            ),
                        }
                    )

        # 6. Invented security domains not in authoritative rules
        auth_domain_names = {
            r.get("name").lower()
            for r in security_rules
            if isinstance(r, dict) and r.get("name")
        }
        for d in security_domains:
            if isinstance(d, dict) and d.get("name"):
                d_name = d.get("name").lower()
                if d_name not in auth_domain_names:
                    errors.append(
                        {
                            "category": "security_domain",
                            "code": "invented_security_rule",
                            "message": (
                                f"Semantic Layer contains invented security domain '{d.get('name')}' "
                                "not supported by authoritative documentation."
                            ),
                        }
                    )

    @staticmethod
    def _check_validation_issues(
        issues: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> None:
        """Report unresolved issues generated during semantic construction."""

        if not isinstance(issues, list):
            return

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

        for field in (
            "semantic_layer_id",
            "revision_id",
            "status",
        ):
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
        """Prevent empty semantic enrichment sections from passing Full Build."""

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

