"""Deterministic T-SQL syntax and read-only structure validation.

The LLM is never the judge of syntax. A real SQL parser is: sqlglot,
configured for the "tsql" dialect, matching the Microsoft SQL Server
target enforced by TEXT_TO_SQL_PROMPT.
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError

from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.application.dto.self_correction.validation_result import ValidationResult

_DIALECT = "tsql"
_SOURCE = "syntax_validator"
_FORBIDDEN_READ_ONLY = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|"
    r"EXEC(?:UTE)?|SELECT\s+INTO|USE|GRANT|REVOKE|DENY|DBCC|BACKUP|RESTORE)\b",
    re.IGNORECASE,
)


class SQLSyntaxValidator:
    """Validates that a SQL string is a single, parseable, read-only T-SQL SELECT."""

    def validate(self, sql: str) -> ValidationResult:
        if not sql or not sql.strip():
            return ValidationResult.fail(
                [
                    ValidationIssue(
                        type="EMPTY_SQL",
                        message="Generated SQL is empty.",
                        source=_SOURCE,
                    )
                ]
            )

        try:
            statements = self.parse_all(sql)
        except ParseError as exc:
            return ValidationResult.fail(
                [
                    ValidationIssue(
                        type="SYNTAX_ERROR",
                        message=str(exc).splitlines()[0],
                        source=_SOURCE,
                    )
                ]
            )

        if len(statements) != 1:
            return ValidationResult.fail(
                [
                    ValidationIssue(
                        type="MULTIPLE_STATEMENTS",
                        message="Only one read-only SQL statement is allowed.",
                        source=_SOURCE,
                    )
                ]
            )

        if _FORBIDDEN_READ_ONLY.search(sql):
            return ValidationResult.fail(
                [
                    ValidationIssue(
                        type="NOT_READ_ONLY",
                        message="Only a read-only SELECT statement is allowed.",
                        source=_SOURCE,
                    )
                ]
            )

        if not isinstance(statements[0], exp.Select):
            return ValidationResult.fail(
                [
                    ValidationIssue(
                        type="NOT_READ_ONLY",
                        message=(
                            "Only a single read-only SELECT statement is allowed; "
                            f"parsed statement type was '{type(statements[0]).__name__}'."
                        ),
                        source=_SOURCE,
                    )
                ]
            )

        return ValidationResult.ok()

    def parse(self, sql: str) -> exp.Expression:
        """Parse SQL into an AST. Raises sqlglot.errors.ParseError on failure.

        Exposed so other components (schema/relationship validators,
        correction context building) can reuse the same parse instead
        of re-parsing the SQL themselves.
        """
        statements = self.parse_all(sql)
        if len(statements) != 1:
            raise ParseError("Expected exactly one SQL statement.")
        return statements[0]

    @staticmethod
    def parse_all(sql: str) -> list[exp.Expression]:
        """Parse every SQL statement so trailing commands cannot be ignored."""
        return sqlglot.parse(sql, dialect=_DIALECT, error_level=ErrorLevel.RAISE)
