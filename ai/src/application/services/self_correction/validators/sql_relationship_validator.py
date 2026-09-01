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
    """Deterministic validator verifying that every SQL JOIN matches an approved relationship.

    Extracts JOIN ON equality conditions from the AST and verifies them against the
    approved Semantic Layer relationships retrieved via the SemanticRepository port.
    """

    def __init__(
        self,
        semantic_repository: SemanticRepository,
        syntax_validator: SQLSyntaxValidator,
        schema_validator: SQLSchemaValidator,
    ) -> None:
        """Initialize the relationship validator.

        Args:
            semantic_repository: Repository providing approved semantic relationships.
            syntax_validator: AST parser for analyzing SQL joins.
            schema_validator: Schema validator for resolving table aliases.
        """
        self._semantic_repository = semantic_repository
        self._syntax_validator = syntax_validator
        self._schema_validator = schema_validator

    def validate(self, sql: str, schema: dict[str, Any] | None = None) -> ValidationResult:
        """Validate that all JOIN clauses in the SQL correspond to approved relationships.

        Args:
            sql: SQL statement string to validate (single or multi-statement).
            schema: Optional physical schema dictionary for alias resolution.

        Returns:
            ValidationResult indicating pass/fail status and any unapproved join issues.
        """
        try:
            statements = self._syntax_validator.parse_all(sql)
        except Exception:
            return ValidationResult.ok()

        alias_map = self._schema_validator.resolve_table_aliases(sql, schema=schema)
        approved_pairs = self._approved_pairs(schema)

        issues: list[ValidationIssue] = []
        already_reported: set[tuple[str, str, str, str]] = set()

        for tree in statements:
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
        relationships = (
            self._semantic_repository.load().get("relationships", [])
            if self._semantic_repository is not None
            else []
        )
        return [
            relationship
            for relationship in relationships
            if relationship.get("from_table") in tables
            and relationship.get("to_table") in tables
            and all(
                isinstance(relationship.get(field), str) and relationship[field]
                for field in ("from_table", "from_column", "to_table", "to_column")
            )
        ]

    def _approved_pairs(
        self, schema: dict[str, Any] | None = None
    ) -> set[tuple[str, str, str, str]]:
        """Return validated semantic pairs, with a source-schema safety fallback.

        A Full Rebuild is required to preserve every source relationship, but
        legacy approved revisions can predate that guarantee or contain only a
        partial relationship projection.  Merge the active Backend schema's
        explicit relationship list as a compatibility source. This does not
        infer a relationship from matching column names; it only retains
        Backend-authoritative join facts until the revision is regenerated.
        """
        relationships = (
            self._semantic_repository.load().get("relationships", [])
            if self._semantic_repository is not None
            else []
        )
        pairs: set[tuple[str, str, str, str]] = set()

        for relationship in relationships:
            from_table = relationship.get("from_table")
            from_column = relationship.get("from_column")
            to_table = relationship.get("to_table")
            to_column = relationship.get("to_column")

            if not all((from_table, from_column, to_table, to_column)):
                continue

            pairs.add((from_table, from_column, to_table, to_column))

        if not isinstance(schema, dict):
            return pairs

        source_relationships = schema.get("relationships", [])
        if not isinstance(source_relationships, list):
            return pairs
        for relationship in source_relationships:
            if not isinstance(relationship, dict):
                continue
            values = tuple(
                relationship.get(field)
                for field in ("from_table", "from_column", "to_table", "to_column")
            )
            if all(isinstance(value, str) and value for value in values):
                pairs.add(values)  # type: ignore[arg-type]
        return pairs

    @staticmethod
    def _is_approved(
        pair: tuple[str, str, str, str],
        approved_pairs: set[tuple[str, str, str, str]],
    ) -> bool:
        left_table, left_col, right_table, right_col = pair
        reversed_pair = (right_table, right_col, left_table, left_col)
        return pair in approved_pairs or reversed_pair in approved_pairs
