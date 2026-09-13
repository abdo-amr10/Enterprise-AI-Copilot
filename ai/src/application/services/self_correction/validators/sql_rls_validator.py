"""Deterministic validation of declarative row-level security (RLS) SQL shape.

The Backend remains the authoritative boundary for authenticated security parameter values.
This validator validates that queries accessing protected domain entities include the declared
parameterized security filters and satisfy the required join paths and predicate equivalence
rules based on active semantic layer metadata.
"""

from __future__ import annotations

import os
import re
from typing import Any
from collections import defaultdict

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


class SQLRlsValidator:
    """Deterministic validator enforcing declared row-level security (RLS) join paths.

    Validates that queries accessing protected domain entities include the required
    parameter filter and satisfy declared propagation join paths and predicate
    equivalence rules based on active semantic layer metadata.
    """

    def __init__(
        self,
        syntax_validator: SQLSyntaxValidator,
        schema_validator: SQLSchemaValidator,
        semantic_repository: Any = None,
    ) -> None:
        """Initialize the RLS validator.

        Args:
            syntax_validator: AST parser for analyzing SQL join and WHERE structures.
            schema_validator: Schema validator for resolving table aliases.
            semantic_repository: Optional semantic repository port for metadata.
        """
        self._syntax_validator = syntax_validator
        self._schema_validator = schema_validator
        self._semantic_repository = semantic_repository
        self._dialect = getattr(syntax_validator, "dialect", os.getenv("SQL_DIALECT", "tsql"))

    def _load_security_domains(self, schema: Any = None) -> list[dict[str, Any]]:
        """Dynamically load security domains from semantic repository or schema metadata."""
        if self._semantic_repository is not None:
            try:
                layer = self._semantic_repository.load()
                if isinstance(layer, dict):
                    domains = layer.get("security_domains")
                    if isinstance(domains, list) and domains:
                        return domains
            except Exception:
                pass

        if isinstance(schema, dict):
            domains = schema.get("security_domains")
            if isinstance(domains, list) and domains:
                return domains

        if self._schema_validator is not None:
            provider = getattr(self._schema_validator, "_schema_provider", None)
            if provider is not None:
                try:
                    s = provider.get_schema()
                    if isinstance(s, dict):
                        domains = s.get("security_domains")
                        if isinstance(domains, list) and domains:
                            return domains
                except Exception:
                    pass

        return []

    def validate(
        self, sql: str, schema: Any = None, enforce_presence: bool = True
    ) -> ValidationResult:
        """Validate that protected tables include proper RLS joins and parameter filters.

        Args:
            sql: SQL statement string to validate (single or multi-statement).
            schema: Optional physical database schema.
            enforce_presence: Whether presence of security parameters is mandatory.

        Returns:
            ValidationResult indicating pass/fail status and any missing RLS mapping issues.
        """
        if not sql or not sql.strip():
            return ValidationResult.ok()

        try:
            statements = self._syntax_validator.parse_all(sql)
        except Exception:
            return ValidationResult.ok()

        if not statements:
            return ValidationResult.ok()

        for stmt_idx, statement in enumerate(statements, 1):
            stmt_sql = statement.sql(dialect=self._dialect)
            result = self._validate_statement(
                statement, stmt_sql, schema=schema, enforce_presence=enforce_presence
            )
            if not result.is_valid:
                return result

        return ValidationResult.ok()

    def _validate_statement(
        self,
        tree: exp.Expression,
        sql: str,
        schema: Any = None,
        enforce_presence: bool = True,
    ) -> ValidationResult:
        """Validate a single statement AST for declarative security compliance across all scopes."""
        security_domains = self._load_security_domains(schema=schema)
        if not security_domains:
            return ValidationResult.ok()

        global_aliases = self._schema_validator.resolve_table_aliases(sql, schema=schema)
        cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
        scopes = list(tree.find_all(exp.Select))
        if not scopes:
            return ValidationResult.ok()

        for scope in scopes:
            result = self._validate_scope(
                scope=scope,
                global_aliases=global_aliases,
                cte_names=cte_names,
                security_domains=security_domains,
                enforce_presence=enforce_presence,
            )
            if not result.is_valid:
                return result

        return ValidationResult.ok()

    def _validate_scope(
        self,
        scope: exp.Select,
        global_aliases: dict[str, str],
        cte_names: set[str],
        security_domains: list[dict[str, Any]],
        enforce_presence: bool = True,
    ) -> ValidationResult:
        """Validate an individual query scope (Select, CTE, derived table, subquery, or UNION branch)."""
        scope_aliases: dict[str, str] = {}
        scope_tables: set[str] = set()

        for t in scope.find_all(exp.Table):
            if t.find_ancestor(exp.Select) is not scope:
                continue
            tbl_name = t.name
            alias_or_name = t.alias_or_name
            if tbl_name in cte_names or alias_or_name in cte_names:
                continue
            real_name = (
                global_aliases.get(alias_or_name)
                or global_aliases.get(tbl_name)
                or tbl_name
            )
            scope_aliases[alias_or_name] = real_name
            scope_aliases[tbl_name] = real_name
            if t.alias:
                scope_aliases[t.alias] = real_name
            if t.db:
                scope_aliases[f"{t.db}.{tbl_name}"] = real_name
            scope_tables.add(real_name)

        if not scope_tables:
            return ValidationResult.ok()

        join_pairs, inner_join_pairs = self._extract_scope_joins(
            scope, scope_aliases, global_aliases
        )

        for domain in security_domains:
            if not isinstance(domain, dict):
                continue

            domain_name = domain.get("name", "unnamed")
            canonical_root = domain.get("canonical_root", "")
            root_table = (
                canonical_root.split(".", 1)[0]
                if "." in canonical_root
                else canonical_root
            )
            root_col = (
                canonical_root.split(".", 1)[1]
                if "." in canonical_root
                else ""
            )

            canonical_predicate = domain.get("canonical_predicate", "")
            param_match = re.search(r"@\w+", canonical_predicate)
            param_name = param_match.group(0) if param_match else "@Parameter"

            propagation_paths = domain.get("propagation_paths", [])
            domain_protected_tables: set[str] = set()
            if root_table:
                domain_protected_tables.add(root_table)
            for p in propagation_paths:
                if isinstance(p, dict) and p.get("target_table"):
                    domain_protected_tables.add(p["target_table"])

            active_protected = scope_tables.intersection(domain_protected_tables)
            if not active_protected:
                continue

            if enforce_presence and not self._scope_has_parameter(scope, param_name):
                hint = (
                    f" (filter {canonical_root} = {param_name})"
                    if canonical_root
                    else ""
                )
                return self._fail(
                    "RLS_PARAMETER_MISSING",
                    f"Query must include the required {param_name} parameter for security domain '{domain_name}'{hint}.",
                )

            raw_filters = self._extract_scope_parameter_filters(
                scope, scope_aliases, param_name, global_aliases
            )
            effective_filters = self._resolve_effective_filters(
                raw_filters, inner_join_pairs, domain
            )

            for table in active_protected:
                if table == root_table:
                    if root_col and (table, root_col) not in effective_filters:
                        issue_code = (
                            "RLS_DIRECT_BRANCH_FILTER_REQUIRED"
                            if root_col == "branch_id"
                            else "RLS_DIRECT_FILTER_REQUIRED"
                        )
                        return self._fail(
                            issue_code,
                            f"For {table}, filter {table}.{root_col} = {param_name}.",
                        )
                else:
                    path_config = next(
                        (
                            p
                            for p in propagation_paths
                            if isinstance(p, dict)
                            and p.get("target_table") == table
                        ),
                        None,
                    )
                    if (
                        path_config is None
                        or path_config.get("propagation") == "not_allowed"
                    ):
                        return self._fail(
                            "RLS_PATH_NOT_ALLOWED",
                            f"Table '{table}' has no allowed security propagation path to '{root_table}'.",
                        )

                    path_str = path_config.get("path", "")
                    required_joins = self._parse_path_joins(path_str)
                    missing_joins = [
                        (t1, c1, t2, c2)
                        for t1, c1, t2, c2 in required_joins
                        if (t1, c1, t2, c2) not in join_pairs
                        and (t2, c2, t1, c1) not in join_pairs
                    ]

                    root_filter_satisfied = (
                        (root_table, root_col) in effective_filters
                        if root_col
                        else bool(effective_filters)
                    )
                    pred_eq = path_config.get("predicate_equivalence")
                    if isinstance(pred_eq, dict) and pred_eq.get("INNER JOIN") is True:
                        target_col = (
                            self._extract_target_col(path_str, table) or root_col
                        )
                        if (table, target_col) in effective_filters:
                            root_filter_satisfied = True

                    if missing_joins or not root_filter_satisfied:
                        issue_code = f"RLS_{table.upper()}_MAPPING_REQUIRED"
                        return self._fail(
                            issue_code,
                            f"For {table}, use path '{path_str}' and filter with {param_name}.",
                        )

        return ValidationResult.ok()

    @staticmethod
    def _fail(issue_type: str, message: str) -> ValidationResult:
        return ValidationResult.fail([ValidationIssue(issue_type, message, _SOURCE)])

    @staticmethod
    def _scope_has_parameter(scope: exp.Select, param_name: str) -> bool:
        """Check whether param_name is present directly within this query scope or attached semijoins."""
        clean = param_name.lstrip("@").casefold()
        for node in scope.find_all(exp.Parameter, exp.Var):
            if node.find_ancestor(exp.Select) is scope:
                if clean in node.sql().lstrip("@").casefold():
                    return True

        for in_exp in scope.find_all(exp.In):
            if in_exp.find_ancestor(exp.Select) is scope:
                query = in_exp.args.get("query")
                if query and clean in query.sql().lstrip("@").casefold():
                    return True

        return False

    @staticmethod
    def _extract_scope_joins(
        scope: exp.Select,
        aliases: dict[str, str],
        global_aliases: dict[str, str] | None = None,
    ) -> tuple[set[tuple[str, str, str, str]], set[tuple[str, str, str, str]]]:
        """Extract join pairs and inner-join pairs belonging directly to this query scope."""
        all_joins: set[tuple[str, str, str, str]] = set()
        inner_joins: set[tuple[str, str, str, str]] = set()
        all_alias_map = {**(global_aliases or {}), **aliases}

        for join in scope.find_all(exp.Join):
            if join.find_ancestor(exp.Select) is not scope:
                continue
            condition = join.args.get("on")
            if condition is None:
                continue

            # Check join type: only INNER JOIN (or unspecified default join) qualifies as inner
            is_inner = True
            kind = str(join.args.get("kind") or "").upper()
            side = str(join.args.get("side") or "").upper()
            if side in {"LEFT", "RIGHT", "FULL", "OUTER"} or kind in {"FULL", "CROSS", "OUTER"}:
                is_inner = False

            for equality in condition.find_all(exp.EQ):
                if equality.find_ancestor(exp.Select) is not scope:
                    continue
                left, right = equality.this, equality.expression
                if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                    continue
                left_table = aliases.get(left.table) or all_alias_map.get(left.table)
                right_table = aliases.get(right.table) or all_alias_map.get(right.table)
                if left_table and right_table:
                    all_joins.add((left_table, left.name, right_table, right.name))
                    all_joins.add((right_table, right.name, left_table, left.name))
                    if is_inner:
                        inner_joins.add((left_table, left.name, right_table, right.name))
                        inner_joins.add((right_table, right.name, left_table, left.name))

        # Check WHERE clause equalities belonging directly to this scope
        where = scope.args.get("where")
        if where:
            for equality in where.find_all(exp.EQ):
                if equality.find_ancestor(exp.Select) is not scope:
                    continue
                left, right = equality.this, equality.expression
                if isinstance(left, exp.Column) and isinstance(right, exp.Column):
                    left_table = aliases.get(left.table) or all_alias_map.get(left.table)
                    right_table = aliases.get(right.table) or all_alias_map.get(right.table)
                    if left_table and right_table:
                        all_joins.add((left_table, left.name, right_table, right.name))
                        all_joins.add((right_table, right.name, left_table, left.name))
                        inner_joins.add((left_table, left.name, right_table, right.name))
                        inner_joins.add((right_table, right.name, left_table, left.name))

        # Check IN subqueries attached directly to this scope (e.g. c.customer_id IN (SELECT customer_id FROM accounts ...))
        for in_exp in scope.find_all(exp.In):
            if in_exp.find_ancestor(exp.Select) is not scope:
                continue
            left = in_exp.this
            query = in_exp.args.get("query")
            if isinstance(left, exp.Column) and query is not None:
                select = query if isinstance(query, exp.Select) else query.find(exp.Select)
                if select and select.expressions:
                    proj = select.expressions[0]
                    proj_col = proj.this if isinstance(proj, exp.Alias) else proj
                    if isinstance(proj_col, exp.Column):
                        left_table = aliases.get(left.table) or all_alias_map.get(left.table)
                        right_table = all_alias_map.get(proj_col.table)
                        if not right_table:
                            sub_tables = [
                                t
                                for t in select.find_all(exp.Table)
                                if t.find_ancestor(exp.Select) is select
                            ]
                            if len(sub_tables) == 1:
                                right_table = (
                                    all_alias_map.get(sub_tables[0].alias_or_name)
                                    or sub_tables[0].name
                                )
                        if left_table and right_table:
                            all_joins.add((left_table, left.name, right_table, proj_col.name))
                            all_joins.add((right_table, proj_col.name, left_table, left.name))
                            inner_joins.add((left_table, left.name, right_table, proj_col.name))
                            inner_joins.add((right_table, proj_col.name, left_table, left.name))

        return all_joins, inner_joins

    @classmethod
    def _extract_joins(
        cls, tree: exp.Expression, aliases: dict[str, str]
    ) -> tuple[set[tuple[str, str, str, str]], set[tuple[str, str, str, str]]]:
        """Backward-compatible wrapper for join extraction."""
        if isinstance(tree, exp.Select):
            return cls._extract_scope_joins(tree, aliases)
        scopes = list(tree.find_all(exp.Select))
        if scopes:
            return cls._extract_scope_joins(scopes[0], aliases)
        return set(), set()

    @staticmethod
    def _parse_path_joins(path_str: str) -> list[tuple[str, str, str, str]]:
        """Parse required join steps from a propagation path expression."""
        joins: list[tuple[str, str, str, str]] = []
        if not path_str:
            return joins

        segments = [s.strip() for s in path_str.split("->") if s.strip()]
        for seg in segments:
            if "=" in seg:
                parts = seg.split("=", 1)
                left_part = parts[0].strip()
                right_part = parts[1].strip()
                if "." in left_part and "." in right_part and not right_part.startswith("@"):
                    t1, c1 = left_part.split(".", 1)
                    t2, c2 = right_part.split(".", 1)
                    joins.append((t1.strip(), c1.strip(), t2.strip(), c2.strip()))
        return joins

    @staticmethod
    def _extract_target_col(path_str: str, target_table: str) -> str | None:
        """Extract column on target table referenced in propagation path."""
        for token in path_str.replace("->", " ").replace("=", " ").split():
            if token.startswith(f"{target_table}."):
                return token.split(".", 1)[1].strip()
        return None

    @staticmethod
    def _extract_scope_parameter_filters(
        scope: exp.Select,
        aliases: dict[str, str],
        param_name: str,
        global_aliases: dict[str, str] | None = None,
    ) -> set[tuple[str, str]]:
        """Extract table.column references compared directly with the security parameter in this scope."""
        filters: set[tuple[str, str]] = set()
        param_pattern = re.compile(rf"^{re.escape(param_name)}$", re.IGNORECASE)
        all_alias_map = {**(global_aliases or {}), **aliases}

        for eq in scope.find_all(exp.EQ):
            if eq.find_ancestor(exp.Select) is not scope:
                continue

            # Guard against exp.Or invalidation: ignore equality predicates nested under an exp.Or within the same scope
            or_ancestor = eq.find_ancestor(exp.Or)
            if or_ancestor and or_ancestor.find_ancestor(exp.Select) is scope:
                continue

            left, right = eq.this, eq.expression
            col_node = (
                left
                if isinstance(left, exp.Column)
                else (right if isinstance(right, exp.Column) else None)
            )
            val_node = (
                right
                if col_node is left
                else (left if col_node is right else None)
            )

            if col_node is None or val_node is None:
                continue

            val_sql = val_node.sql().strip().strip("'\"")
            if param_pattern.fullmatch(val_sql):
                table_name = aliases.get(col_node.table) or all_alias_map.get(col_node.table)
                if not table_name:
                    local_tables = [
                        t
                        for t in scope.find_all(exp.Table)
                        if t.find_ancestor(exp.Select) is scope
                    ]
                    if len(local_tables) == 1:
                        table_name = (
                            aliases.get(local_tables[0].alias_or_name)
                            or local_tables[0].name
                        )
                if table_name:
                    filters.add((table_name, col_node.name))

        # Check parameter filters from approved IN subqueries attached to this scope
        for in_exp in scope.find_all(exp.In):
            if in_exp.find_ancestor(exp.Select) is not scope:
                continue
            query = in_exp.args.get("query")
            if query is not None:
                sub_select = query if isinstance(query, exp.Select) else query.find(exp.Select)
                if sub_select:
                    for sub_eq in sub_select.find_all(exp.EQ):
                        if sub_eq.find_ancestor(exp.Select) is not sub_select:
                            continue
                        sub_or = sub_eq.find_ancestor(exp.Or)
                        if sub_or and sub_or.find_ancestor(exp.Select) is sub_select:
                            continue
                        sub_l, sub_r = sub_eq.this, sub_eq.expression
                        s_col = (
                            sub_l
                            if isinstance(sub_l, exp.Column)
                            else (sub_r if isinstance(sub_r, exp.Column) else None)
                        )
                        s_val = (
                            sub_r
                            if s_col is sub_l
                            else (sub_l if s_col is sub_r else None)
                        )
                        if (
                            s_col
                            and s_val
                            and param_pattern.fullmatch(s_val.sql().strip().strip("'\""))
                        ):
                            sub_tbl = all_alias_map.get(s_col.table)
                            if not sub_tbl:
                                sub_local_t = [
                                    t
                                    for t in sub_select.find_all(exp.Table)
                                    if t.find_ancestor(exp.Select) is sub_select
                                ]
                                if len(sub_local_t) == 1:
                                    sub_tbl = (
                                        all_alias_map.get(sub_local_t[0].alias_or_name)
                                        or sub_local_t[0].name
                                    )
                            if sub_tbl:
                                filters.add((sub_tbl, s_col.name))

        return filters

    @classmethod
    def _extract_parameter_filters(
        cls, tree: exp.Expression, aliases: dict[str, str], param_name: str
    ) -> set[tuple[str, str]]:
        """Backward-compatible wrapper for parameter filter extraction."""
        if isinstance(tree, exp.Select):
            return cls._extract_scope_parameter_filters(tree, aliases, param_name)
        scopes = list(tree.find_all(exp.Select))
        if scopes:
            return cls._extract_scope_parameter_filters(scopes[0], aliases, param_name)
        return set()

    @classmethod
    def _resolve_effective_filters(
        cls,
        raw_filters: set[tuple[str, str]],
        inner_joins: set[tuple[str, str, str, str]],
        domain: dict[str, Any],
    ) -> set[tuple[str, str]]:
        """Build equivalence classes over approved INNER JOINs and propagate filter satisfaction."""
        if not raw_filters:
            return set()

        canonical_root = domain.get("canonical_root", "")
        root_col = canonical_root.split(".", 1)[1] if "." in canonical_root else ""

        # Build adjacency graph over (table, column) pairs connected via INNER JOIN
        adj: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
        for t1, c1, t2, c2 in inner_joins:
            if (root_col and c1.lower() == root_col.lower() and c2.lower() == root_col.lower()) or (c1.lower() == c2.lower()):
                adj[(t1, c1)].add((t2, c2))
                adj[(t2, c2)].add((t1, c1))

        effective = set(raw_filters)
        for node in list(raw_filters):
            queue = [node]
            visited = {node}
            while queue:
                curr = queue.pop(0)
                effective.add(curr)
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

        return effective