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
            sql: SQL statement string to validate (single or multi-statement).
            schema: Optional pre-loaded schema dictionary; if None, queries schema_provider.

        Returns:
            ValidationResult indicating pass/fail status and UNKNOWN_TABLE / UNKNOWN_COLUMN issues.
        """
        try:
            statements = self._syntax_validator.parse_all(sql)
        except Exception:
            return ValidationResult.ok()  # Syntax validator handles syntax errors

        tables = (schema or self._schema_provider.get_schema())["tables"]
        issues: list[ValidationIssue] = []

        for tree in statements:
            alias_map, unknown_tables = self._resolve_tables(tree, tables)

            for table in sorted(unknown_tables):
                issues.append(
                    ValidationIssue(
                        type="UNKNOWN_TABLE",
                        message=f"Table '{table}' does not exist in the physical database schema.",
                        source=_SOURCE,
                    )
                )

            issues.extend(self._validate_columns(tree, alias_map, unknown_tables, tables))
            issues.extend(self._validate_aggregate_types(tree, alias_map, unknown_tables, tables))

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
        try:
            statements = self._syntax_validator.parse_all(sql)
        except Exception:
            return {}

        tables = (schema or self._schema_provider.get_schema())["tables"]
        combined_alias_map: dict[str, str] = {}
        for tree in statements:
            alias_map, _ = self._resolve_tables(tree, tables)
            combined_alias_map.update(alias_map)
        return combined_alias_map

    def qualify_base_table_projection_ambiguities(
        self, sql: str, schema: dict[str, Any] | None = None
    ) -> str:
        """Safely qualify ambiguous, unqualified columns in the outer SELECT list.

        This is a narrow normalisation step for simple LLM output. It never
        rewrites predicates, JOIN conditions, grouping, CTEs, subqueries, or
        UNIONs because choosing a table in those scopes could change a query's
        meaning. When the base ``FROM`` table is unambiguous, qualifying only
        a projected column preserves the intended result and prevents a
        downstream ``AMBIGUOUS_COLUMN`` error.
        """
        try:
            statements = self._syntax_validator.parse_all(sql)
        except Exception:
            # Syntax validation is responsible for reporting malformed SQL.
            return sql

        if not statements:
            return sql

        schema_tables = (schema or self._schema_provider.get_schema()).get("tables", {})
        rebuilt_stmts: list[str] = []

        for tree in statements:
            # Scope-aware rewriting of these query forms needs a resolver; leave
            # them untouched and let deterministic validation/self-correction act.
            if any(tree.find(node_type) for node_type in (exp.CTE, exp.Subquery, exp.Union)):
                rebuilt_stmts.append(tree.sql(dialect="tsql"))
                continue

            select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
            if select is None:
                rebuilt_stmts.append(tree.sql(dialect="tsql"))
                continue

            from_clause = select.args.get("from_")
            base_table = from_clause.this if from_clause is not None else None
            if not isinstance(base_table, exp.Table):
                rebuilt_stmts.append(tree.sql(dialect="tsql"))
                continue

            base_table_name = base_table.name
            base_definition = schema_tables.get(base_table_name)
            if base_definition is None:
                rebuilt_stmts.append(tree.sql(dialect="tsql"))
                continue

            alias_map, unknown_tables = self._resolve_tables(tree, schema_tables)
            if unknown_tables:
                rebuilt_stmts.append(tree.sql(dialect="tsql"))
                continue

            base_alias = base_table.alias_or_name
            base_columns = {
                column["name"] for column in base_definition.get("columns", [])
            }
            referenced_tables = set(alias_map.values())

            for projection in select.expressions:
                for column in projection.find_all(exp.Column):
                    if column.table or column.name not in base_columns:
                        continue

                    candidates = [
                        table_name
                        for table_name in referenced_tables
                        if column.name
                        in {
                            item["name"]
                            for item in schema_tables.get(table_name, {}).get("columns", [])
                        }
                    ]
                    if len(candidates) > 1:
                        column.set("table", exp.to_identifier(base_alias))

            rebuilt_stmts.append(tree.sql(dialect="tsql"))

        return ";\n".join(rebuilt_stmts)

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
    def _extract_cte_projections(tree: exp.Expression) -> dict[str, set[str]]:
        """Map CTE name/alias -> set of column names projected by that CTE."""
        cte_projections: dict[str, set[str]] = {}
        for cte in tree.find_all(exp.CTE):
            cte_name = cte.alias_or_name
            # 1. Check if CTE has explicit column aliases: WITH cte(col1, col2) AS (...)
            alias_node = cte.args.get("alias")
            if alias_node and hasattr(alias_node, "columns") and alias_node.columns:
                cte_projections[cte_name] = {
                    c.name for c in alias_node.columns if hasattr(c, "name") and c.name
                }
                continue

            # 2. Otherwise extract projected columns from the CTE's inner select
            cols: set[str] = set()
            cte_query = cte.this
            select_node = (
                cte_query
                if isinstance(cte_query, exp.Select)
                else (cte_query.find(exp.Select) if cte_query else None)
            )
            if select_node:
                for expr in select_node.expressions:
                    if isinstance(expr, exp.Alias) and expr.alias:
                        cols.add(expr.alias)
                    elif isinstance(expr, exp.Column) and expr.name:
                        cols.add(expr.name)
                    elif hasattr(expr, "alias_or_name") and expr.alias_or_name:
                        cols.add(expr.alias_or_name)
                    elif hasattr(expr, "name") and expr.name:
                        cols.add(expr.name)
            cte_projections[cte_name] = cols
        return cte_projections

    @staticmethod
    def _enclosing_select(column: exp.Column) -> exp.Select | None:
        """Find the innermost enclosing Select statement for a column AST node."""
        curr = column.parent
        while curr is not None:
            if isinstance(curr, exp.Select):
                return curr
            curr = curr.parent
        return None

    @staticmethod
    def _sources_in_select(
        select: exp.Select,
        cte_projections: dict[str, set[str]],
        schema_tables: dict,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Return (cte_sources, physical_sources) mapping alias/name -> table/cte name in scope."""
        cte_sources: dict[str, str] = {}
        physical_sources: dict[str, str] = {}

        # Check FROM clause
        from_clause = select.args.get("from_")
        if from_clause is not None and from_clause.this is not None:
            source_table = from_clause.this
            if isinstance(source_table, exp.Table):
                table_name = source_table.name
                alias_or_name = source_table.alias_or_name
                if table_name in cte_projections:
                    cte_sources[alias_or_name] = table_name
                elif table_name in schema_tables:
                    physical_sources[alias_or_name] = table_name

        # Check JOIN clauses
        for join in select.args.get("joins", []):
            join_table = join.this
            if isinstance(join_table, exp.Table):
                table_name = join_table.name
                alias_or_name = join_table.alias_or_name
                if table_name in cte_projections:
                    cte_sources[alias_or_name] = table_name
                elif table_name in schema_tables:
                    physical_sources[alias_or_name] = table_name

        return cte_sources, physical_sources

    @classmethod
    def _validate_columns(
        cls,
        tree: exp.Expression,
        alias_map: dict[str, str],
        unknown_tables: set[str],
        schema_tables: dict,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        already_reported: set[tuple[str, str]] = set()
        cte_projections = cls._extract_cte_projections(tree)

        select_aliases = {
            expression.alias
            for expression in tree.find_all(exp.Alias)
            if expression.alias
        }

        for column in tree.find_all(exp.Column):
            table_ref = column.table
            column_name = column.name

            enclosing_select = cls._enclosing_select(column)
            if enclosing_select is not None:
                cte_sources, physical_sources = cls._sources_in_select(
                    enclosing_select, cte_projections, schema_tables
                )
            else:
                cte_sources, physical_sources = {}, {
                    k: v for k, v in alias_map.items() if v in schema_tables
                }

            # -------------------------------------------------------------
            # Unqualified column
            # -------------------------------------------------------------
            if not table_ref:
                if column_name in select_aliases:
                    continue

                if cte_sources or physical_sources:
                    candidates: list[str] = []
                    # Check CTE sources in scope
                    for cte_alias, cte_name in cte_sources.items():
                        proj_cols = cte_projections.get(cte_name, set())
                        if column_name in proj_cols or not proj_cols:
                            candidates.append(cte_alias)

                    # Check physical table sources in scope
                    for phys_alias, phys_table in physical_sources.items():
                        if phys_table in schema_tables:
                            known_cols = {
                                col["name"]
                                for col in schema_tables[phys_table].get("columns", [])
                            }
                            if column_name in known_cols:
                                candidates.append(phys_table)

                    unique_candidates = sorted(set(candidates))
                    if not unique_candidates:
                        issues.append(
                            ValidationIssue(
                                type="UNKNOWN_COLUMN",
                                message=f"Unqualified column '{column_name}' does not exist in the query scope.",
                                source=_SOURCE,
                            )
                        )
                    elif len(unique_candidates) > 1:
                        issues.append(
                            ValidationIssue(
                                type="AMBIGUOUS_COLUMN",
                                message=f"Unqualified column '{column_name}' is ambiguous across {unique_candidates}.",
                                source=_SOURCE,
                            )
                        )
                    continue

                candidates = [
                    table_name
                    for table_name in set(alias_map.values())
                    if column_name
                    in {
                        col["name"]
                        for col in schema_tables.get(table_name, {}).get("columns", [])
                    }
                ]
                if not candidates:
                    issues.append(
                        ValidationIssue(
                            type="UNKNOWN_COLUMN",
                            message=f"Unqualified column '{column_name}' does not exist in the query scope.",
                            source=_SOURCE,
                        )
                    )
                elif len(candidates) > 1:
                    issues.append(
                        ValidationIssue(
                            type="AMBIGUOUS_COLUMN",
                            message=f"Unqualified column '{column_name}' is ambiguous across {sorted(candidates)}.",
                            source=_SOURCE,
                        )
                    )
                continue

            # -------------------------------------------------------------
            # Qualified column
            # -------------------------------------------------------------
            if table_ref in cte_sources or table_ref in cte_projections:
                cte_name = cte_sources.get(table_ref, table_ref)
                proj_cols = cte_projections.get(cte_name, set())
                if proj_cols and column_name not in proj_cols:
                    issues.append(
                        ValidationIssue(
                            type="UNKNOWN_COLUMN",
                            message=f"Column '{table_ref}.{column_name}' does not exist in CTE '{cte_name}'.",
                            source=_SOURCE,
                        )
                    )
                continue

            real_table = alias_map.get(table_ref)
            if real_table is None:
                # Alias belongs to a CTE or could not be resolved; out of scope for physical schema checks.
                continue

            if real_table in unknown_tables:
                # Already reported as UNKNOWN_TABLE; avoid duplicate noise.
                continue

            key = (real_table, column_name)
            if key in already_reported:
                continue
            already_reported.add(key)

            known_columns = {
                col["name"] for col in schema_tables.get(real_table, {}).get("columns", [])
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

    @classmethod
    def _validate_aggregate_types(
        cls,
        tree: exp.Expression,
        alias_map: dict[str, str],
        unknown_tables: set[str],
        schema_tables: dict,
    ) -> list[ValidationIssue]:
        """Validate that numeric aggregate functions (AVG, SUM, STDEV, VARIANCE) are applied to numeric columns."""
        issues: list[ValidationIssue] = []

        NUMERIC_AGG_TYPES = tuple(
            cls
            for name in ("Avg", "Sum", "Stddev", "StddevPop", "StddevSamp", "Variance", "VariancePop", "Var")
            if (cls := getattr(exp, name, None)) is not None
        )
        NON_NUMERIC_TYPE_PREFIXES = (
            "varchar",
            "nvarchar",
            "char",
            "nchar",
            "text",
            "ntext",
            "date",
            "datetime",
            "datetime2",
            "smalldatetime",
            "time",
            "datetimeoffset",
            "timestamp",
            "bit",
            "uniqueidentifier",
            "binary",
            "varbinary",
            "image",
            "xml",
        )

        def _is_cast_to_numeric(col_node: exp.Column, top_node: exp.Expression) -> bool:
            curr = col_node.parent
            while curr is not None and curr is not top_node:
                if isinstance(curr, (exp.Cast, exp.TryCast)):
                    to_type = str(curr.to).lower()
                    if not any(to_type.startswith(p) for p in NON_NUMERIC_TYPE_PREFIXES):
                        return True
                curr = curr.parent
            return False

        def _resolve_real_table(table_ref: str | None, column_name: str) -> str | None:
            if table_ref:
                return alias_map.get(table_ref, table_ref)
            candidates = [
                t_name
                for t_name in set(alias_map.values())
                if t_name in schema_tables
                and column_name
                in {c["name"] for c in schema_tables[t_name].get("columns", []) if isinstance(c, dict) and "name" in c}
            ]
            if len(candidates) == 1:
                return candidates[0]
            return None

        # Check standard AST aggregate nodes
        for agg_node in tree.find_all(NUMERIC_AGG_TYPES):
            agg_name = agg_node.key.upper()
            for column in agg_node.find_all(exp.Column):
                if _is_cast_to_numeric(column, agg_node):
                    continue

                real_table = _resolve_real_table(column.table, column.name)
                if not real_table or real_table in unknown_tables or real_table not in schema_tables:
                    continue

                col_defs = {
                    c["name"]: c.get("type") or c.get("data_type", "")
                    for c in schema_tables[real_table].get("columns", [])
                    if isinstance(c, dict) and "name" in c
                }
                raw_type = str(col_defs.get(column.name, "")).strip().lower()
                if not raw_type:
                    continue

                if any(raw_type.startswith(prefix) for prefix in NON_NUMERIC_TYPE_PREFIXES):
                    issues.append(
                        ValidationIssue(
                            type="TYPE_MISMATCH",
                            message=(
                                f"Cannot apply aggregation function '{agg_name}' to "
                                f"non-numeric column '{real_table}.{column.name}' of type '{raw_type}'."
                            ),
                            source=_SOURCE,
                        )
                    )

        # Check anonymous function calls (e.g. custom/dialect specific AVG/SUM)
        for anon in tree.find_all(exp.Anonymous):
            func_name = anon.name.upper()
            if func_name in {"AVG", "SUM", "STDEV", "VARIANCE"}:
                for column in anon.find_all(exp.Column):
                    if _is_cast_to_numeric(column, anon):
                        continue

                    real_table = _resolve_real_table(column.table, column.name)
                    if not real_table or real_table in unknown_tables or real_table not in schema_tables:
                        continue

                    col_defs = {
                        c["name"]: c.get("type") or c.get("data_type", "")
                        for c in schema_tables[real_table].get("columns", [])
                        if isinstance(c, dict) and "name" in c
                    }
                    raw_type = str(col_defs.get(column.name, "")).strip().lower()
                    if any(raw_type.startswith(prefix) for prefix in NON_NUMERIC_TYPE_PREFIXES):
                        issues.append(
                            ValidationIssue(
                                type="TYPE_MISMATCH",
                                message=(
                                    f"Cannot apply aggregation function '{func_name}' to "
                                    f"non-numeric column '{real_table}.{column.name}' of type '{raw_type}'."
                                ),
                                source=_SOURCE,
                            )
                        )

        return issues

