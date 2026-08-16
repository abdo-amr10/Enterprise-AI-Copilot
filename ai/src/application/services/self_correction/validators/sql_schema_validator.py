"""Deterministic table/column existence validation.

Tables and columns referenced by the generated SQL are checked
against the physical database schema (docs/database_metadata/schema.json,
normalized through the existing SchemaLoader). This is the ground
truth for "does this table/column physically exist" -- the approved
Semantic Layer alone does not carry column-level detail for every
section, so it is not sufficient for this specific check.
"""

from __future__ import annotations

from sqlglot import exp

from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.application.dto.self_correction.validation_result import ValidationResult
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)
from src.application.ports.physical_schema_repository import PhysicalSchemaRepository

_SOURCE = "schema_validator"


class SQLSchemaValidator:
    """Validates that every referenced table and qualified column exists."""

    def __init__(
        self,
        schema_provider: PhysicalSchemaRepository,
        syntax_validator: SQLSyntaxValidator,
    ) -> None:
        self._schema_provider = schema_provider
        self._syntax_validator = syntax_validator

    def validate(self, sql: str) -> ValidationResult:
        tree = self._syntax_validator.parse(sql)
        tables = self._schema_provider.get_schema()["tables"]

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

    def extract_tables(self, sql: str) -> set[str]:
        """Return the set of real (schema) table names referenced by sql.

        Reused by SelfCorrectionService to build the "relevant schema"
        slice passed to the Correction LLM prompt -- so table
        extraction logic lives in exactly one place.
        """
        return set(self.resolve_table_aliases(sql).values())

    def schema_slice(self, sql: str) -> dict[str, dict]:
        """Return {table_name: table_definition} for tables referenced by sql.

        Reused by SelfCorrectionService to build the "relevant schema"
        slice passed to the Correction LLM prompt, instead of sending
        the entire database schema on every correction attempt.
        """
        tables = self.extract_tables(sql)
        all_tables = self._schema_provider.get_schema()["tables"]
        return {name: all_tables[name] for name in tables if name in all_tables}

    def resolve_table_aliases(self, sql: str) -> dict[str, str]:
        """Return {alias_or_table_name: real_table_name} for sql, excluding CTEs.

        Reused by SQLRelationshipValidator so alias resolution is not
        re-implemented for JOIN-condition checking.
        """
        tree = self._syntax_validator.parse(sql)
        tables = self._schema_provider.get_schema()["tables"]
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

        for column in tree.find_all(exp.Column):
            table_ref = column.table
            column_name = column.name

            if not table_ref:
                # Unqualified column (e.g. an output alias or a single-table
                # query): cannot be resolved reliably without risking a
                # false positive, so it is intentionally not flagged here.
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
