"""Deterministic validation of the Backend's parameterized RLS SQL shape.

The Backend remains the authority for the authenticated branch value and binds
``@UserBranchId`` at execution time.  This validator mirrors its documented
table-to-branch join mapping so the AI returns an executable, branch-scoped
query before the Backend receives it.
"""

from __future__ import annotations

import re

from sqlglot import exp

from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.application.dto.self_correction.validation_result import ValidationResult
from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)

_SOURCE = "rls_validator"
_BRANCH_PARAMETER = re.compile(r"^@USERBRANCHID$", re.IGNORECASE)


class SQLRlsValidator:
    """Deterministic validator enforcing required row-level security (RLS) join paths.

    Validates that queries accessing protected domain entities (loans, accounts, cards, customers)
    include the Backend's parameterized `@UserBranchId` filter and satisfy the required
    table-to-branch join sequence before execution.
    """

    def __init__(
        self, syntax_validator: SQLSyntaxValidator, schema_validator: SQLSchemaValidator
    ) -> None:
        """Initialize the RLS validator.

        Args:
            syntax_validator: AST parser for analyzing SQL join and WHERE structures.
            schema_validator: Schema validator for resolving table aliases.
        """
        self._syntax_validator = syntax_validator
        self._schema_validator = schema_validator

    def validate(
        self, sql: str, schema: Any = None, enforce_presence: bool = True
    ) -> ValidationResult:
        """Validate that protected tables include proper RLS branch joins and parameter filters.

        Args:
            sql: SQL statement string to validate.
            schema: Optional physical database schema.
            enforce_presence: Whether presence of `@UserBranchId` is mandatory.

        Returns:
            ValidationResult indicating pass/fail status and any missing RLS mapping issues.
        """
        if "@UserBranchId".casefold() not in sql.casefold():
            if enforce_presence:
                return self._fail(
                    "RLS_PARAMETER_MISSING",
                    "Query must include the Backend-bound @UserBranchId parameter.",
                )
            return ValidationResult.ok()

        tree = self._syntax_validator.parse(sql)
        aliases = self._schema_validator.resolve_table_aliases(sql)
        tables = set(aliases.values())
        joins = self._join_pairs(tree, aliases)
        branch_filters = self._branch_filters(tree, aliases)

        # These ordered policies are intentionally the same as the Backend's
        # ValidateRlsMapping precedence. A loans query is governed by its full
        # loans path, rather than independently by its customer join.
        if "loans" in tables:
            required = {
                ("loans", "customer_id", "customers", "customer_id"),
                ("customers", "customer_id", "accounts", "customer_id"),
                ("accounts", "branch_id", "branches", "branch_id"),
            }
            if not required.issubset(joins) or ("branches", "branch_id") not in branch_filters:
                return self._fail(
                    "RLS_LOANS_MAPPING_REQUIRED",
                    "For loans, use loans -> customers -> accounts -> branches and filter branches.branch_id = @UserBranchId.",
                )
            return ValidationResult.ok()

        if "merchants" in tables:
            required = {
                ("merchants", "merchant_id", "transactions", "merchant_id"),
                ("transactions", "account_id", "accounts", "account_id"),
            }
            if not required.issubset(joins) or ("accounts", "branch_id") not in branch_filters:
                return self._fail(
                    "RLS_MERCHANTS_MAPPING_REQUIRED",
                    "For merchants, join merchants -> transactions -> accounts and filter accounts.branch_id = @UserBranchId.",
                )
            return ValidationResult.ok()

        if "customers" in tables and (
            ("customers", "customer_id", "accounts", "customer_id") not in joins
            or ("accounts", "branch_id") not in branch_filters
        ):
            return self._fail(
                "RLS_CUSTOMERS_MAPPING_REQUIRED",
                "For customers, join customers.customer_id = accounts.customer_id and filter accounts.branch_id = @UserBranchId.",
            )

        for table in ("transactions", "cards"):
            if table in tables and (
                (table, "account_id", "accounts", "account_id") not in joins
                or ("accounts", "branch_id") not in branch_filters
            ):
                return self._fail(
                    "RLS_ACCOUNT_MAPPING_REQUIRED",
                    f"For {table}, join {table}.account_id = accounts.account_id and filter accounts.branch_id = @UserBranchId.",
                )

        for table in ("branches", "accounts"):
            if table in tables and (table, "branch_id") not in branch_filters:
                return self._fail(
                    "RLS_DIRECT_BRANCH_FILTER_REQUIRED",
                    f"For {table}, filter {table}.branch_id = @UserBranchId.",
                )

        return ValidationResult.ok()

    @staticmethod
    def _fail(issue_type: str, message: str) -> ValidationResult:
        return ValidationResult.fail([ValidationIssue(issue_type, message, _SOURCE)])

    @staticmethod
    def _join_pairs(
        tree: exp.Expression, aliases: dict[str, str]
    ) -> set[tuple[str, str, str, str]]:
        pairs: set[tuple[str, str, str, str]] = set()
        for join in tree.find_all(exp.Join):
            condition = join.args.get("on")
            if condition is None:
                continue
            for equality in condition.find_all(exp.EQ):
                left, right = equality.this, equality.expression
                if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                    continue
                left_table, right_table = aliases.get(left.table), aliases.get(right.table)
                if left_table and right_table:
                    pairs.add((left_table, left.name, right_table, right.name))
                    pairs.add((right_table, right.name, left_table, left.name))
        return pairs

    @staticmethod
    def _branch_filters(
        tree: exp.Expression, aliases: dict[str, str]
    ) -> set[tuple[str, str]]:
        filters: set[tuple[str, str]] = set()
        for where in tree.find_all(exp.Where):
            for equality in where.find_all(exp.EQ):
                left, right = equality.this, equality.expression
                column = left if isinstance(left, exp.Column) else right if isinstance(right, exp.Column) else None
                value = right if column is left else left if column is right else None
                if column is None or value is None or not _BRANCH_PARAMETER.fullmatch(value.sql()):
                    continue
                table = aliases.get(column.table)
                if table:
                    filters.add((table, column.name))
        return filters
