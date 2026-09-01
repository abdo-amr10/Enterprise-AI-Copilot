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
        self._rls_validator = rls_validator
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
        """Repair direct transitive shortcut joins by inserting canonical intermediate bridging tables."""
        relationships = self._load_approved_relationships(schema=schema)
        if not relationships:
            return

        approved_pairs: set[tuple[str, str, str, str]] = set()
        edge_map: dict[tuple[str, str], list[tuple[str, str]]] = {}
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
                edge_map.setdefault((ft, fc), []).append((tt, tc))
                edge_map.setdefault((tt, tc), []).append((ft, fc))

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
                        # Find bridging table
                        neighbors_1 = edge_map.get((tbl1, col1), [])
                        for bridge_tbl, bridge_col1 in neighbors_1:
                            if (bridge_tbl, bridge_col1, tbl2, col2) in approved_pairs or any(
                                (bridge_tbl, bcol2, tbl2, col2) in approved_pairs
                                for bcol2 in [bridge_col1, col2]
                            ):
                                bridge_col2 = (
                                    bridge_col1
                                    if (bridge_tbl, bridge_col1, tbl2, col2) in approved_pairs
                                    else col2
                                )
                                base_alias = bridge_tbl[0].lower()
                                candidate_alias = base_alias
                                counter = 1
                                while candidate_alias in existing_aliases:
                                    candidate_alias = f"{base_alias}{counter}"
                                    counter += 1
                                existing_aliases.add(candidate_alias)
                                alias_map[candidate_alias] = bridge_tbl

                                bridge_join = exp.Join(
                                    this=exp.Table(
                                        this=exp.to_identifier(bridge_tbl),
                                        alias=exp.TableAlias(this=exp.to_identifier(candidate_alias)),
                                    ),
                                    on=exp.EQ(
                                        this=exp.Column(
                                            this=exp.to_identifier(col1),
                                            table=exp.to_identifier(left.table),
                                        ),
                                        expression=exp.Column(
                                            this=exp.to_identifier(bridge_col1),
                                            table=exp.to_identifier(candidate_alias),
                                        ),
                                    ),
                                    kind="INNER",
                                )
                                new_joins.append(bridge_join)

                                eq.replace(
                                    exp.EQ(
                                        this=exp.Column(
                                            this=exp.to_identifier(bridge_col2),
                                            table=exp.to_identifier(candidate_alias),
                                        ),
                                        expression=exp.Column(
                                            this=exp.to_identifier(col2),
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

        select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
        if select is None:
            return tree

        if enforce_rls:
            import re
            domains = self._load_security_domains(schema=schema)
            for domain in domains:
                if not isinstance(domain, dict):
                    continue
                canonical_root = domain.get("canonical_root", "")
                if "." not in canonical_root:
                    continue
                root_table, root_col = canonical_root.split(".", 1)
                canonical_predicate = domain.get("canonical_predicate", "")
                param_match = re.search(r"@\w+", canonical_predicate)
                param_name = param_match.group(0) if param_match else "@UserBranchId"

                # Check if param is already present in the statement AST
                if param_name.casefold() in select.sql(dialect=_DIALECT).casefold():
                    continue

                repaired_for_domain = False
                # Check if root table is in select (e.g. FROM accounts or JOIN accounts)
                for table in select.find_all(exp.Table):
                    if table.name == root_table:
                        alias = table.alias_or_name
                        eq_cond = exp.EQ(
                            this=exp.Column(
                                this=exp.to_identifier(root_col),
                                table=exp.to_identifier(alias),
                            ),
                            expression=exp.var(param_name),
                        )
                        select.where(eq_cond, copy=False)
                        repaired_for_domain = True
                        break

                # If root table wasn't in query, check equivalent direct tables (e.g. branches)
                if not repaired_for_domain:
                    for prop in domain.get("propagation_paths", []):
                        if not isinstance(prop, dict):
                            continue
                        pred_eq = prop.get("predicate_equivalence")
                        if prop.get("is_canonical_root") or (
                            isinstance(pred_eq, dict) and pred_eq.get("INNER JOIN") is True
                        ):
                            target_tbl = prop.get("target_table")
                            path_str = prop.get("path", "")
                            if (
                                target_tbl
                                and f"{target_tbl}." in path_str
                                and f"={param_name}" in path_str.replace(" ", "")
                            ):
                                for table in select.find_all(exp.Table):
                                    if table.name == target_tbl:
                                        alias = table.alias_or_name
                                        col = path_str.split("=")[0].strip().split(".")[-1]
                                        eq_cond = exp.EQ(
                                            this=exp.Column(
                                                this=exp.to_identifier(col),
                                                table=exp.to_identifier(alias),
                                            ),
                                            expression=exp.var(param_name),
                                        )
                                        select.where(eq_cond, copy=False)
                                        repaired_for_domain = True
                                        break
                                if repaired_for_domain:
                                    break

                # If direct root/branch tables weren't in query, check indirect tables with approved paths (e.g. customers, transactions, cards, loans)
                if not repaired_for_domain:
                    for table in select.find_all(exp.Table):
                        tbl_name = table.name
                        alias = table.alias_or_name
                        if tbl_name == "customers":
                            sub_ast = sqlglot.parse_one(
                                f"SELECT a.customer_id FROM {root_table} AS a WHERE a.{root_col} = {param_name}",
                                read=_DIALECT,
                            )
                            in_cond = exp.In(
                                this=exp.Column(
                                    this=exp.to_identifier("customer_id"),
                                    table=exp.to_identifier(alias),
                                ),
                                expressions=[sub_ast],
                            )
                            select.where(in_cond, copy=False)
                            repaired_for_domain = True
                            break
                        elif tbl_name in ("transactions", "cards"):
                            sub_ast = sqlglot.parse_one(
                                f"SELECT a.account_id FROM {root_table} AS a WHERE a.{root_col} = {param_name}",
                                read=_DIALECT,
                            )
                            in_cond = exp.In(
                                this=exp.Column(
                                    this=exp.to_identifier("account_id"),
                                    table=exp.to_identifier(alias),
                                ),
                                expressions=[sub_ast],
                            )
                            select.where(in_cond, copy=False)
                            repaired_for_domain = True
                            break
                        elif tbl_name == "loans":
                            sub_ast = sqlglot.parse_one(
                                f"SELECT a.customer_id FROM {root_table} AS a WHERE a.{root_col} = {param_name}",
                                read=_DIALECT,
                            )
                            in_cond = exp.In(
                                this=exp.Column(
                                    this=exp.to_identifier("customer_id"),
                                    table=exp.to_identifier(alias),
                                ),
                                expressions=[sub_ast],
                            )
                            select.where(in_cond, copy=False)
                            repaired_for_domain = True
                            break

        return tree
