"""Deterministic T-SQL syntax and read-only structure validation.

The LLM is never the judge of syntax. A real SQL parser is: sqlglot,
configured for the "tsql" dialect, matching the Microsoft SQL Server
target enforced by TEXT_TO_SQL_PROMPT.
"""

from __future__ import annotations

import os
import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError

from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.application.dto.self_correction.validation_result import ValidationResult

_DIALECT = os.getenv("SQL_DIALECT", "tsql")
_SOURCE = "syntax_validator"
_FORBIDDEN_READ_ONLY = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|"
    r"EXEC(?:UTE)?|SELECT\s+INTO|USE|GRANT|REVOKE|DENY|DBCC|BACKUP|RESTORE)\b",
    re.IGNORECASE,
)


class SQLSyntaxValidator:
    """Deterministic validator enforcing valid read-only SQL syntax.

    Uses `sqlglot` configured for the target SQL dialect (defaulting to Microsoft SQL Server `tsql`)
    to ensure that candidate queries are strictly read-only SELECT queries (single or multi-statement)
    without destructive commands, DDL/DML, dynamic SQL, or syntax errors.
    """

    _FORBIDDEN_NODE_TYPES = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Merge,
        exp.Drop,
        exp.Alter,
        exp.Create,
        exp.Command,
    )

    def __init__(self, dialect: str | None = None) -> None:
        self._dialect = dialect or os.getenv("SQL_DIALECT", "tsql")

    @property
    def dialect(self) -> str:
        return self._dialect

    def validate(self, sql: str) -> ValidationResult:
        """Validate that a SQL string consists only of parseable, read-only T-SQL SELECT queries.

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
        except (ParseError, Exception) as exc:
            return ValidationResult.fail(
                [
                    ValidationIssue(
                        type="SYNTAX_ERROR",
                        message=str(exc).splitlines()[0] if str(exc) else "SQL syntax parsing error.",
                        source=_SOURCE,
                    )
                ]
            )

        if not statements:
            return ValidationResult.fail(
                [
                    ValidationIssue(
                        type="EMPTY_SQL",
                        message="Generated SQL contains no executable statements.",
                        source=_SOURCE,
                    )
                ]
            )

        if _FORBIDDEN_READ_ONLY.search(sql):
            return ValidationResult.fail(
                [
                    ValidationIssue(
                        type="NOT_READ_ONLY",
                        message="Only read-only SELECT statements are allowed; forbidden keyword detected.",
                        source=_SOURCE,
                    )
                ]
            )

        for idx, statement in enumerate(statements, 1):
            # Check AST node types
            for forbidden_type in self._FORBIDDEN_NODE_TYPES:
                if isinstance(statement, forbidden_type) or statement.find(forbidden_type):
                    return ValidationResult.fail(
                        [
                            ValidationIssue(
                                type="NOT_READ_ONLY",
                                message=(
                                    f"Statement {idx} is not read-only. "
                                    f"Forbidden node '{forbidden_type.__name__}' detected."
                                ),
                                source=_SOURCE,
                            )
                        ]
                    )

            if not (isinstance(statement, exp.Select) or statement.find(exp.Select)):
                return ValidationResult.fail(
                    [
                        ValidationIssue(
                            type="NOT_READ_ONLY",
                            message=(
                                f"Statement {idx} must be a read-only SELECT query; "
                                f"parsed statement type was '{type(statement).__name__}'."
                            ),
                            source=_SOURCE,
                        )
                    ]
                )

        return ValidationResult.ok()

    def parse(self, sql: str) -> exp.Expression:
        """Parse a SQL statement string into an AST expression.

        Args:
            sql: SQL statement string.

        Returns:
            The parsed sqlglot AST Expression (first statement if multiple).

        Raises:
            ParseError: If the SQL cannot be parsed or contains no statements.
        """
        statements = self.parse_all(sql, dialect=self._dialect)
        if not statements:
            raise ParseError("Expected at least one SQL statement.")
        return statements[0]

    @classmethod
    def parse_all(cls, sql: str, dialect: str | None = None) -> list[exp.Expression]:
        """Parse all SQL statements in a string into AST expressions.

        Args:
            sql: SQL text containing one or more statements.
            dialect: Optional dialect string override.

        Returns:
            List of parsed sqlglot AST Expressions.

        Raises:
            ParseError: If syntax errors occur during parsing.
        """
        target_dialect = dialect or _DIALECT
        return [stmt for stmt in sqlglot.parse(sql, dialect=target_dialect, error_level=ErrorLevel.RAISE) if stmt is not None]
