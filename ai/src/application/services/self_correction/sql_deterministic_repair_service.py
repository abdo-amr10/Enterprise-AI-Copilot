"""Deterministic AST-based SQL repair service.

Operates directly on the parsed SQL AST to apply safe, unambiguous, and idempotent
transformations before invoking expensive LLM self-correction loops.

Repairs supported:
1. Ambiguous projection qualification for base table projections.
2. DISTINCT semantics and fanout pre-aggregation preservation.
3. Idempotent transformation: repair(repair(SQL)) == repair(SQL).
"""

from __future__ import annotations

import logging
from typing import Any
import sqlglot
from sqlglot import exp

from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)
from src.application.services.self_correction.validators.sql_rls_validator import (
    SQLRlsValidator,
)

logger = logging.getLogger(__name__)

_DIALECT = "tsql"


class SQLDeterministicRepairService:
    """Performs safe, idempotent, AST-level repairs on SQL queries."""

    def __init__(
        self,
        syntax_validator: SQLSyntaxValidator,
        schema_validator: SQLSchemaValidator,
        rls_validator: SQLRlsValidator | None = None,
        relationship_validator: Any = None,
    ) -> None:
        self._syntax_validator = syntax_validator
        self._schema_validator = schema_validator
        self._rls_validator = rls_validator or SQLRlsValidator(
            syntax_validator=syntax_validator,
            schema_validator=schema_validator,
        )
        self._relationship_validator = relationship_validator

    def repair(
        self,
        sql: str,
        schema: dict[str, Any] | None = None,
        enforce_rls: bool = True,
    ) -> str:
        """Repair candidate SQL deterministically on the AST.

        Args:
            sql: SQL statement string (single or multi-statement).
            schema: Optional physical database schema dictionary.
            enforce_rls: Whether to inject missing RLS branch parameter filters.

        Returns:
            Repaired SQL statement string.
        """
        if not sql or not sql.strip():
            return sql

        try:
            statements = self._syntax_validator.parse_all(sql)
        except Exception:
            return sql

        if not statements:
            return sql

        repaired_statements: list[exp.Expression] = []

        for statement in statements:
            repaired = self._repair_single_statement(
                statement, schema=schema, enforce_rls=enforce_rls
            )
            repaired_statements.append(repaired)

        repaired_sql = ";\n".join(stmt.sql(dialect=_DIALECT) for stmt in repaired_statements)
        if len(repaired_statements) == 1 and not sql.strip().endswith(";"):
            pass
        elif sql.strip().endswith(";") and not repaired_sql.endswith(";"):
            repaired_sql = repaired_sql + ";"

        # Projection ambiguities qualification
        try:
            qualifier = getattr(
                self._schema_validator, "qualify_base_table_projection_ambiguities", None
            )
            if callable(qualifier):
                repaired_sql = qualifier(repaired_sql, schema=schema)
        except Exception:
            pass

        return repaired_sql

    def _load_approved_relationships(
        self, schema: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Load approved relationships from relationship validator or schema."""
        if self._relationship_validator is not None:
            repo = getattr(self._relationship_validator, "_semantic_repository", None)
            if repo is not None:
                try:
                    rels = repo.load().get("relationships", [])
                    if rels:
                        return rels
                except Exception:
                    pass
        if isinstance(schema, dict):
            rels = schema.get("relationships")
            if isinstance(rels, list) and rels:
                return rels
        return []

    def _load_security_domains(self, schema: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Load active security domains from RLS validator or schema."""
        if self._rls_validator is not None:
            loader = getattr(self._rls_validator, "_load_security_domains", None)
            if callable(loader):
                try:
                    domains = loader(schema=schema)
                    if domains:
                        return domains
                except Exception:
                    pass
        if isinstance(schema, dict):
            domains = schema.get("security_domains")
            if isinstance(domains, list) and domains:
                return domains
        return []

    def _repair_unapproved_joins(
        self,
        select: exp.Select,
        schema: dict[str, Any] | None = None,
    ) -> None:
        """Repair direct transitive shortcut joins by inserting canonical intermediate bridging tables.

        Uses table-level adjacency to discover bridge tables that connect two
        tables lacking a direct approved relationship, regardless of which side
        is the from_table in the approved relationship definitions.
        """
        relationships = self._load_approved_relationships(schema=schema)
        if not relationships:
            return

        approved_pairs: set[tuple[str, str, str, str]] = set()
        # table_adj: table -> set of tables it has ANY approved relationship with
        table_adj: dict[str, set[str]] = {}
        # rel_columns: (tbl_a, tbl_b) -> list of (col_a, col_b) approved column pairs
        rel_columns: dict[tuple[str, str], list[tuple[str, str]]] = {}

        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            ft, fc, tt, tc = (
                rel.get("from_table"),
                rel.get("from_column"),
                rel.get("to_table"),
                rel.get("to_column"),
            )
            if ft and fc and tt and tc:
                approved_pairs.add((ft, fc, tt, tc))
                approved_pairs.add((tt, tc, ft, fc))
                # Build bidirectional table-level adjacency
                table_adj.setdefault(ft, set()).add(tt)
                table_adj.setdefault(tt, set()).add(ft)
                # Store column pairs in both directions for lookup
                rel_columns.setdefault((ft, tt), []).append((fc, tc))
                rel_columns.setdefault((tt, ft), []).append((tc, fc))

        alias_map = self._schema_validator.resolve_table_aliases(
            select.sql(dialect=_DIALECT), schema=schema
        )

        joins = list(select.args.get("joins", []))
        if not joins:
            return

        new_joins: list[exp.Join] = []
        modified = False

        existing_aliases = {
            t.alias_or_name.lower()
            for t in select.find_all(exp.Table)
            if t.alias_or_name
        }

        for join in joins:
            on_condition = join.args.get("on")
            if on_condition is None:
                new_joins.append(join)
                continue

            eq_nodes = list(on_condition.find_all(exp.EQ))
            bridged = False
            for eq in eq_nodes:
                left, right = eq.this, eq.expression
                if isinstance(left, exp.Column) and isinstance(right, exp.Column):
                    tbl1 = alias_map.get(left.table)
                    tbl2 = alias_map.get(right.table)
                    col1 = left.name
                    col2 = right.name

                    if not tbl1 or not tbl2:
                        continue

                    if (tbl1, col1, tbl2, col2) not in approved_pairs:
                        # Find bridge tables adjacent to BOTH tbl1 and tbl2
                        neighbors_1 = table_adj.get(tbl1, set())
                        neighbors_2 = table_adj.get(tbl2, set())
                        bridge_candidates = (neighbors_1 & neighbors_2) - {tbl1, tbl2}

                        for bridge_tbl in bridge_candidates:
                            # Look up approved column pairs for bridge->tbl1 and bridge->tbl2
                            cols_to_tbl1 = rel_columns.get((bridge_tbl, tbl1), [])
                            cols_to_tbl2 = rel_columns.get((bridge_tbl, tbl2), [])

                            if not cols_to_tbl1 or not cols_to_tbl2:
                                continue

                            # Use the first valid column pair for each leg
                            bridge_col_for_tbl1, tbl1_join_col = cols_to_tbl1[0]
                            bridge_col_for_tbl2, tbl2_join_col = cols_to_tbl2[0]

                            # Generate a unique alias for the bridge table
                            base_alias = bridge_tbl[0].lower()
                            candidate_alias = base_alias
                            counter = 1
                            while candidate_alias in existing_aliases:
                                candidate_alias = f"{base_alias}{counter}"
                                counter += 1
                            existing_aliases.add(candidate_alias)
                            alias_map[candidate_alias] = bridge_tbl

                            # Create the bridge JOIN (bridge_table to tbl1)
                            bridge_join = exp.Join(
                                this=exp.Table(
                                    this=exp.to_identifier(bridge_tbl),
                                    alias=exp.TableAlias(this=exp.to_identifier(candidate_alias)),
                                ),
                                on=exp.EQ(
                                    this=exp.Column(
                                        this=exp.to_identifier(tbl1_join_col),
                                        table=exp.to_identifier(left.table),
                                    ),
                                    expression=exp.Column(
                                        this=exp.to_identifier(bridge_col_for_tbl1),
                                        table=exp.to_identifier(candidate_alias),
                                    ),
                                ),
                                kind="INNER",
                            )
                            new_joins.append(bridge_join)

                            # Replace the original unapproved ON condition
                            # with the bridge->tbl2 leg
                            eq.replace(
                                exp.EQ(
                                    this=exp.Column(
                                        this=exp.to_identifier(bridge_col_for_tbl2),
                                        table=exp.to_identifier(candidate_alias),
                                    ),
                                    expression=exp.Column(
                                        this=exp.to_identifier(tbl2_join_col),
                                        table=exp.to_identifier(right.table),
                                    ),
                                )
                            )
                            new_joins.append(join)
                            bridged = True
                            modified = True
                            break
                    if bridged:
                        break
            if not bridged:
                new_joins.append(join)

        if modified:
            select.set("joins", new_joins)

    @staticmethod
    def _apply_dynamic_rls_joins(
        select: exp.Select,
        tbl_name: str,
        alias: str,
        path_str: str,
        param_name: str,
        existing_aliases: set[str] | None = None,
    ) -> bool:
        """Dynamically attach required RLS propagation INNER JOINs and WHERE predicate to the select statement."""
        if not path_str or "->" not in path_str:
            return False

        segments = [s.strip() for s in path_str.split("->") if s.strip()]
        if not segments:
            return False

        if existing_aliases is None:
            existing_aliases = {
                t.alias_or_name.lower()
                for t in select.find_all(exp.Table)
                if t.alias_or_name
            }

        table_alias_map = {
            t.name.lower(): t.alias_or_name
            for t in select.find_all(exp.Table)
            if t.find_ancestor(exp.Select) is select and t.name
        }
        if tbl_name and alias:
            table_alias_map[tbl_name.lower()] = alias

        alias_counter = 1
        joins_to_add: list[exp.Join] = []
        where_cond: exp.Expression | None = None

        for seg in segments:
            if "=" not in seg:
                continue
            seg_left, seg_right = [x.strip() for x in seg.split("=", 1)]

            if seg_right.startswith("@") or seg_left.startswith("@"):
                col_side = seg_left if not seg_left.startswith("@") else seg_right
                if "." in col_side:
                    r_tbl, r_col = col_side.split(".", 1)
                    r_alias = table_alias_map.get(r_tbl.lower(), r_tbl)
                    where_cond = exp.EQ(
                        this=exp.Column(
                            this=exp.to_identifier(r_col),
                            table=exp.to_identifier(r_alias),
                        ),
                        expression=exp.var(param_name),
                    )
            else:
                if "." in seg_left and "." in seg_right:
                    t1, c1 = seg_left.split(".", 1)
                    t2, c2 = seg_right.split(".", 1)
                    t1_lower, t2_lower = t1.lower(), t2.lower()

                    t1_alias = table_alias_map.get(t1_lower)
                    t2_alias = table_alias_map.get(t2_lower)

                    if t1_alias and not t2_alias:
                        base_alias = t2[0].lower()
                        cand_alias = base_alias
                        while cand_alias.lower() in existing_aliases:
                            cand_alias = f"{base_alias}{alias_counter}"
                            alias_counter += 1
                        existing_aliases.add(cand_alias.lower())
                        table_alias_map[t2_lower] = cand_alias

                        join_node = exp.Join(
                            this=exp.Table(
                                this=exp.to_identifier(t2),
                                alias=exp.TableAlias(this=exp.to_identifier(cand_alias)),
                            ),
                            on=exp.EQ(
                                this=exp.Column(
                                    this=exp.to_identifier(c1),
                                    table=exp.to_identifier(t1_alias),
                                ),
                                expression=exp.Column(
                                    this=exp.to_identifier(c2),
                                    table=exp.to_identifier(cand_alias),
                                ),
                            ),
                            kind="INNER",
                        )
                        joins_to_add.append(join_node)

                    elif t2_alias and not t1_alias:
                        base_alias = t1[0].lower()
                        cand_alias = base_alias
                        while cand_alias.lower() in existing_aliases:
                            cand_alias = f"{base_alias}{alias_counter}"
                            alias_counter += 1
                        existing_aliases.add(cand_alias.lower())
                        table_alias_map[t1_lower] = cand_alias

                        join_node = exp.Join(
                            this=exp.Table(
                                this=exp.to_identifier(t1),
                                alias=exp.TableAlias(this=exp.to_identifier(cand_alias)),
                            ),
                            on=exp.EQ(
                                this=exp.Column(
                                    this=exp.to_identifier(c2),
                                    table=exp.to_identifier(t2_alias),
                                ),
                                expression=exp.Column(
                                    this=exp.to_identifier(c1),
                                    table=exp.to_identifier(cand_alias),
                                ),
                            ),
                            kind="INNER",
                        )
                        joins_to_add.append(join_node)

        if not joins_to_add and not where_cond:
            return False

        if joins_to_add:
            select.args.setdefault("joins", []).extend(joins_to_add)

        if where_cond is not None:
            where_node = select.args.get("where")
            where_sql = where_node.sql(dialect=_DIALECT).casefold() if where_node else ""
            cond_sql = where_cond.sql(dialect=_DIALECT).casefold()
            if cond_sql not in where_sql:
                select.where(where_cond, copy=False)

        return True

    def _repair_single_statement(
        self,
        tree: exp.Expression,
        schema: dict[str, Any] | None = None,
        enforce_rls: bool = True,
    ) -> exp.Expression:
        """Repair an individual Select statement AST."""
        tree = tree.copy()

        for select in tree.find_all(exp.Select):
            try:
                self._repair_unapproved_joins(select, schema=schema)
            except Exception:
                pass

        if not enforce_rls:
            return tree

        import re

        domains = self._load_security_domains(schema=schema)
        if not domains:
            return tree

        global_aliases = self._schema_validator.resolve_table_aliases(
            tree.sql(dialect=_DIALECT), schema=schema
        )
        cte_names = {
            cte.alias_or_name.lower()
            for cte in tree.find_all(exp.CTE)
            if cte.alias_or_name
        }

        all_tree_aliases = {
            t.alias_or_name.lower()
            for t in tree.find_all(exp.Table)
            if t.alias_or_name
        }

        # Repair scopes innermost to outermost (reverse preorder traversal).
        # This ensures inner subqueries and CTEs are repaired before outer scopes evaluate semijoins.
        scopes = list(tree.find_all(exp.Select))[::-1]

        for scope in scopes:
            # Find tables belonging directly to this scope
            scope_tables: dict[str, str] = {}
            for t in scope.find_all(exp.Table):
                if t.find_ancestor(exp.Select) is not scope:
                    continue
                tbl_name = t.name
                alias_or_name = t.alias_or_name
                if not tbl_name:
                    continue
                if tbl_name.lower() in cte_names or alias_or_name.lower() in cte_names:
                    continue
                real_name = (
                    global_aliases.get(alias_or_name)
                    or global_aliases.get(tbl_name)
                    or tbl_name
                )
                scope_tables[real_name.lower()] = alias_or_name

            if not scope_tables:
                continue

            for domain in domains:
                if not isinstance(domain, dict):
                    continue
                canonical_root = domain.get("canonical_root", "")
                if "." not in canonical_root:
                    continue
                root_table, root_col = canonical_root.split(".", 1)
                root_table_lower = root_table.lower()
                canonical_predicate = domain.get("canonical_predicate", "")
                param_match = re.search(r"@\w+", canonical_predicate)
                param_name = param_match.group(0) if param_match else "@UserBranchId"

                propagation_paths = domain.get("propagation_paths", [])
                domain_protected: set[str] = {root_table_lower}
                paths_by_table: dict[str, dict[str, Any]] = {}
                for p in propagation_paths:
                    if isinstance(p, dict) and p.get("target_table"):
                        tgt = p["target_table"].lower()
                        domain_protected.add(tgt)
                        paths_by_table[tgt] = p

                active_protected = set(scope_tables.keys()).intersection(domain_protected)
                if not active_protected:
                    continue

                # Validate if this scope already satisfies RLS for this domain
                if self._rls_validator is not None:
                    val_res = self._rls_validator._validate_scope(
                        scope=scope,
                        global_aliases=global_aliases,
                        cte_names=cte_names,
                        security_domains=[domain],
                        enforce_presence=True,
                    )
                    if val_res.is_valid:
                        continue

                # Sort active_protected by propagation path depth (hop count) descending
                # so deeper multi-hop paths (e.g. loans -> customers -> accounts -> branches)
                # are repaired first, fulfilling intermediate table join requirements.
                def _hop_count(tbl: str) -> int:
                    if tbl == root_table_lower:
                        return 0
                    p_entry = paths_by_table.get(tbl)
                    if not p_entry:
                        return 0
                    p_str = p_entry.get("path", "")
                    return p_str.count("->") + 1 if p_str else 0

                sorted_protected = sorted(active_protected, key=_hop_count, reverse=True)

                for tbl in sorted_protected:
                    alias = scope_tables[tbl]
                    p_entry = paths_by_table.get(tbl)
                    path_str = p_entry.get("path", "") if p_entry else ""

                    if path_str and "->" in path_str:
                        self._apply_dynamic_rls_joins(
                            select=scope,
                            tbl_name=tbl,
                            alias=alias,
                            path_str=path_str,
                            param_name=param_name,
                            existing_aliases=all_tree_aliases,
                        )
                    elif tbl == root_table_lower:
                        where_node = scope.args.get("where")
                        where_sql = where_node.sql(dialect=_DIALECT).casefold() if where_node else ""
                        if param_name.casefold() not in where_sql:
                            eq_cond = exp.EQ(
                                this=exp.Column(
                                    this=exp.to_identifier(root_col),
                                    table=exp.to_identifier(alias),
                                ),
                                expression=exp.var(param_name),
                            )
                            scope.where(eq_cond, copy=False)
                    elif p_entry and (
                        p_entry.get("is_canonical_root")
                        or (
                            isinstance(p_entry.get("predicate_equivalence"), dict)
                            and p_entry["predicate_equivalence"].get("INNER JOIN") is True
                        )
                    ):
                        where_node = scope.args.get("where")
                        where_sql = where_node.sql(dialect=_DIALECT).casefold() if where_node else ""
                        if param_name.casefold() not in where_sql:
                            col = path_str.split("=")[0].strip().split(".")[-1] if "=" in path_str else root_col
                            eq_cond = exp.EQ(
                                this=exp.Column(
                                    this=exp.to_identifier(col),
                                    table=exp.to_identifier(alias),
                                ),
                                expression=exp.var(param_name),
                            )
                            scope.where(eq_cond, copy=False)

                    # Check if scope is now valid
                    if self._rls_validator is not None:
                        val_res = self._rls_validator._validate_scope(
                            scope=scope,
                            global_aliases=global_aliases,
                            cte_names=cte_names,
                            security_domains=[domain],
                            enforce_presence=True,
                        )
                        if val_res.is_valid:
                            break

        return tree
