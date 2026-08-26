"""Deterministic table/column existence validation.

Tables and columns referenced by the generated SQL are checked
against Backend-provided physical database schema metadata, normalized through
the existing SchemaLoader. This is the ground truth for "does this table/column
physically exist" -- the approved
Semantic Layer alone does not carry column-level detail for every
section, so it is not sufficient for this specific check.
"""

from __future__ import annotations

from typing import Any
from sqlglot import exp

from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.application.dto.self_correction.validation_result import ValidationResult
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)
from src.application.ports.physical_schema_repository import PhysicalSchemaRepository

_SOURCE = "schema_validator"


class SQLSchemaValidator:
    """Deterministic validator verifying that referenced tables and columns exist in the physical schema.

    Parses table references and qualified column identifiers from the AST and validates them
    against the authoritative database schema provided by PhysicalSchemaRepository.
    """

    def __init__(
        self,
        schema_provider: PhysicalSchemaRepository,
        syntax_validator: SQLSyntaxValidator,
    ) -> None:
        """Initialize the schema validator.

        Args:
            schema_provider: Authoritative source for physical database schema metadata.
            syntax_validator: AST parser for SQL analysis.
        """
        self._schema_provider = schema_provider
        self._syntax_validator = syntax_validator

    def validate(self, sql: str, schema: dict[str, Any] | None = None) -> ValidationResult:
        """Validate that all tables and qualified columns in the SQL exist in the schema.

        Args:
            sql: SQL statement string to validate.
            schema: Optional pre-loaded schema dictionary; if None, queries schema_provider.

        Returns:
            ValidationResult indicating pass/fail status and UNKNOWN_TABLE / UNKNOWN_COLUMN issues.
        """
        tree = self._syntax_validator.parse(sql)
        tables = (schema or self._schema_provider.get_schema())["tables"]

        alias_map, unknown_tables = self._resolve_tables(tree, tables)

        issues: list[ValidationIssue] = [
            ValidationIssue(
                type="UNKNOWN_TABLE",
                message=f"Table '{table}' does not exist in the physical database schema.",
                source=_SOURCE,
            )
            for table in sorted(unknown_tables)
        ]

        issues.extend(self._validate_columns(tree, alias_map, unknown_tables, tables))

        if issues:
            return ValidationResult.fail(issues)
        return ValidationResult.ok()

    def extract_tables(self, sql: str, schema: dict[str, Any] | None = None) -> set[str]:
        """Extract the set of real physical table names referenced by a SQL query.

        Args:
            sql: SQL statement string to inspect.
            schema: Optional pre-loaded physical database schema.

        Returns:
            Set of physical table name strings referenced in the query.
        """
        return set(self.resolve_table_aliases(sql, schema=schema).values())

    def schema_slice(self, sql: str, schema: dict[str, Any] | None = None) -> dict[str, dict]:
        """Extract a minimal schema subset containing only tables referenced by the query.

        Args:
            sql: SQL statement string.
            schema: Optional pre-loaded physical database schema.

        Returns:
            Dictionary mapping referenced table names to their table definitions.
        """
        tables = self.extract_tables(sql, schema=schema)
        all_tables = (schema or self._schema_provider.get_schema())["tables"]
        return {name: all_tables[name] for name in tables if name in all_tables}

    def resolve_table_aliases(self, sql: str, schema: dict[str, Any] | None = None) -> dict[str, str]:
        """Resolve table aliases and table names to real schema table names, excluding CTEs.

        Args:
            sql: SQL statement string.
            schema: Optional pre-loaded physical database schema.

        Returns:
            Dictionary mapping table aliases (or unaliased table names) to real table names.
        """
        tree = self._syntax_validator.parse(sql)
        tables = (schema or self._schema_provider.get_schema())["tables"]
        alias_map, _ = self._resolve_tables(tree, tables)
        return alias_map

    @staticmethod
    def _resolve_tables(
        tree: exp.Expression,
        schema_tables: dict,
    ) -> tuple[dict[str, str], set[str]]:
        """Map alias -> real table name, excluding CTE names, and collect unknowns."""

        cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}

        alias_map: dict[str, str] = {}
        unknown_tables: set[str] = set()

        for table in tree.find_all(exp.Table):
            real_name = table.name
            if real_name in cte_names:
                continue

            alias_map[table.alias_or_name] = real_name

            if real_name not in schema_tables:
                unknown_tables.add(real_name)

        return alias_map, unknown_tables

    @staticmethod
    def _validate_columns(
        tree: exp.Expression,
        alias_map: dict[str, str],
        unknown_tables: set[str],
        schema_tables: dict,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        already_reported: set[tuple[str, str]] = set()
        select_aliases = {
            expression.alias
            for expression in tree.find_all(exp.Alias)
            if expression.alias
        }

        for column in tree.find_all(exp.Column):
            table_ref = column.table
            column_name = column.name

            if not table_ref:
                if column_name in select_aliases:
                    continue
                candidates = [
                    table_name
                    for table_name in set(alias_map.values())
                    if column_name in {col["name"] for col in schema_tables.get(table_name, {}).get("columns", [])}
                ]
                if not candidates:
                    issues.append(ValidationIssue(
                        type="UNKNOWN_COLUMN",
                        message=f"Unqualified column '{column_name}' does not exist in the query scope.",
                        source=_SOURCE,
                    ))
                elif len(candidates) > 1:
                    issues.append(ValidationIssue(
                        type="AMBIGUOUS_COLUMN",
                        message=f"Unqualified column '{column_name}' is ambiguous across {sorted(candidates)}.",
                        source=_SOURCE,
                    ))
                continue

            real_table = alias_map.get(table_ref)
            if real_table is None:
                # Alias belongs to a CTE or could not be resolved; the CTE's
                # own projection is out of scope for physical schema checks.
                continue

            if real_table in unknown_tables:
                # Already reported as UNKNOWN_TABLE; avoid duplicate noise.
                continue

            key = (real_table, column_name)
            if key in already_reported:
                continue
            already_reported.add(key)

            known_columns = {
                col["name"] for col in schema_tables[real_table]["columns"]
            }

            if column_name not in known_columns:
                issues.append(
                    ValidationIssue(
                        type="UNKNOWN_COLUMN",
                        message=(
                            f"Column '{real_table}.{column_name}' does not exist "
                            "in the physical database schema."
                        ),
                        source=_SOURCE,
                    )
                )

        return issues
