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
    """Deterministic validator enforcing valid single-statement read-only T-SQL syntax.

    Uses `sqlglot` configured for the Microsoft SQL Server (`tsql`) dialect to ensure
    that candidate queries are strictly single-statement read-only SELECT queries without
    destructive commands, DDL/DML, or syntax errors.
    """

    def validate(self, sql: str) -> ValidationResult:
        """Validate that a SQL string is a single, parseable, read-only T-SQL SELECT query.

        Args:
            sql: SQL statement string to validate.

        Returns:
            ValidationResult indicating pass/fail status and any detected ValidationIssues.
        """
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
        """Parse a single SQL statement into an AST expression.

        Args:
            sql: Single SQL statement string.

        Returns:
            The parsed sqlglot AST Expression.

        Raises:
            ParseError: If the SQL cannot be parsed or contains multiple statements.
        """
        statements = self.parse_all(sql)
        if len(statements) != 1:
            raise ParseError("Expected exactly one SQL statement.")
        return statements[0]

    @staticmethod
    def parse_all(sql: str) -> list[exp.Expression]:
        """Parse all SQL statements in a string into AST expressions.

        Args:
            sql: SQL text containing one or more statements.

        Returns:
            List of parsed sqlglot AST Expressions.

        Raises:
            ParseError: If syntax errors occur during parsing.
        """
        return sqlglot.parse(sql, dialect=_DIALECT, error_level=ErrorLevel.RAISE)
