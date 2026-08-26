"""Deterministic JOIN/relationship validation.

Every JOIN condition is checked against the relationships recorded in
the *approved* Semantic Layer (the same source the Backend marks
Approved after human review), reusing the existing SemanticRepository
port instead of a separate relationship store. A JOIN whose ON clause
does not correspond to an approved relationship (in either direction)
is rejected even when it is syntactically valid SQL.
"""

from __future__ import annotations

from typing import Any

from sqlglot import exp

from src.application.ports.semantic_repository import SemanticRepository
from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.application.dto.self_correction.validation_result import ValidationResult
from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)

_SOURCE = "relationship_validator"


class SQLRelationshipValidator:
    """Validates that every JOIN uses an approved relationship."""

    def __init__(
        self,
        semantic_repository: SemanticRepository,
        syntax_validator: SQLSyntaxValidator,
        schema_validator: SQLSchemaValidator,
    ) -> None:
        self._semantic_repository = semantic_repository
        self._syntax_validator = syntax_validator
        self._schema_validator = schema_validator

    def validate(self, sql: str, schema: dict[str, Any] | None = None) -> ValidationResult:
        tree = self._syntax_validator.parse(sql)
        alias_map = self._schema_validator.resolve_table_aliases(sql, schema=schema)
        approved_pairs = self._approved_pairs()

        issues: list[ValidationIssue] = []
        already_reported: set[tuple[str, str, str, str]] = set()

        for join in tree.find_all(exp.Join):
            on_condition = join.args.get("on")
            if on_condition is None:
                issues.append(
                    ValidationIssue(
                        type="MISSING_JOIN_CONDITION",
                        message="Every table join must have a column-to-column ON condition matching an approved relationship.",
                        source=_SOURCE,
                    )
                )
                continue

            for eq in on_condition.find_all(exp.EQ):
                left, right = eq.this, eq.expression

                if not (isinstance(left, exp.Column) and isinstance(right, exp.Column)):
                    # Not a simple column-to-column equality (e.g. a filter
                    # such as `a.status = 'active'`) -- out of scope here.
                    continue

                left_table = alias_map.get(left.table)
                right_table = alias_map.get(right.table)

                if left_table is None or right_table is None:
                    # Unresolved/unknown table -- already reported by
                    # SQLSchemaValidator, avoid duplicate noise.
                    continue

                pair = (left_table, left.name, right_table, right.name)
                if pair in already_reported:
                    continue

                if not self._is_approved(pair, approved_pairs):
                    already_reported.add(pair)
                    issues.append(
                        ValidationIssue(
                            type="INVALID_RELATIONSHIP",
                            message=(
                                f"JOIN condition '{left_table}.{left.name} = "
                                f"{right_table}.{right.name}' is not an approved "
                                "relationship."
                            ),
                            source=_SOURCE,
                        )
                    )

        if issues:
            return ValidationResult.fail(issues)
        return ValidationResult.ok()

    def relationships_for_tables(self, tables: set[str]) -> list[dict[str, Any]]:
        """Return approved relationships connecting any two of the given tables.

        Reused by SelfCorrectionService to build the "relevant
        relationships" slice passed to the Correction LLM prompt.
        """
        return [
            relationship
            for relationship in self._semantic_repository.load().get("relationships", [])
            if relationship.get("from_table") in tables
            and relationship.get("to_table") in tables
        ]

    def _approved_pairs(self) -> set[tuple[str, str, str, str]]:
        relationships = self._semantic_repository.load().get("relationships", [])
        pairs: set[tuple[str, str, str, str]] = set()

        for relationship in relationships:
            from_table = relationship.get("from_table")
            from_column = relationship.get("from_column")
            to_table = relationship.get("to_table")
            to_column = relationship.get("to_column")

            if not all((from_table, from_column, to_table, to_column)):
                continue

            pairs.add((from_table, from_column, to_table, to_column))

        return pairs

    @staticmethod
    def _is_approved(
        pair: tuple[str, str, str, str],
        approved_pairs: set[tuple[str, str, str, str]],
    ) -> bool:
        left_table, left_col, right_table, right_col = pair
        reversed_pair = (right_table, right_col, left_table, left_col)
        return pair in approved_pairs or reversed_pair in approved_pairs
