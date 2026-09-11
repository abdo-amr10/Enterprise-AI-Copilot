"""Authoritative security and RLS rule extractor for documentation sources."""

from __future__ import annotations

import re
from typing import Any
from collections import Counter


class SecurityRuleExtractor:
    """Extract and normalize authoritative Security/RLS metadata from Documentation."""

    @classmethod
    def extract_security_rules(cls, documentation: str | None) -> list[dict[str, Any]]:
        """Extract authoritative security domains from documentation markdown or text.

        Returns an empty list if documentation is None, empty, or contains no
        recognizable RLS/security rules. Never fabricates undocumented rules.
        """
        if not documentation or not isinstance(documentation, str) or not documentation.strip():
            return []

        # 1. Parse raw table rules from documentation
        raw_rules = cls._parse_raw_rules(documentation)
        if not raw_rules:
            return []

        # 2. Group raw rules into security domains based on parameter and predicate root
        domains = cls._group_into_domains(raw_rules)
        return domains

    @classmethod
    def _parse_raw_rules(cls, documentation: str) -> list[dict[str, Any]]:
        """Parse raw table rules from markdown tables, block colon, or bullet formats."""
        lines = documentation.splitlines()
        raw_rules: list[dict[str, Any]] = []

        in_rls_section = False

        # First pass: try markdown table format
        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith("#"):
                header_text = trimmed.lstrip("#").strip().lower()
                in_rls_section = any(
                    keyword in header_text
                    for keyword in ("rls", "security", "data filtering", "row-level", "row level")
                )
                continue

            if in_rls_section and trimmed.startswith("|") and not trimmed.startswith("|---"):
                parts = [p.strip().strip("`") for p in trimmed.split("|")[1:-1]]
                if len(parts) >= 3:
                    col0_lower = parts[0].lower()
                    if col0_lower in ("table", "entity", "target table", "target_table", "---"):
                        continue
                    target_table = col0_lower
                    join_logic = parts[1]
                    enforced_sql = parts[2]
                    parsed = cls._parse_sql_expression(target_table, enforced_sql, join_logic)
                    if parsed:
                        raw_rules.append(parsed)

        if raw_rules:
            return raw_rules

        # Second pass: Block/colon or bullet list format
        current_table: str | None = None
        current_sql_lines: list[str] = []

        def flush_block():
            nonlocal current_table, current_sql_lines
            if current_table and current_sql_lines:
                sql_text = " ".join(current_sql_lines).strip()
                parsed = cls._parse_sql_expression(current_table, sql_text)
                if parsed:
                    raw_rules.append(parsed)
            current_table = None
            current_sql_lines = []

        in_rls_section = False
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                flush_block()
                continue

            if trimmed.startswith("#"):
                flush_block()
                header_text = trimmed.lstrip("#").strip().lower()
                in_rls_section = any(
                    keyword in header_text
                    for keyword in ("rls", "security", "data filtering", "row-level", "row level")
                )
                continue

            # Check if line looks like header without markdown hashes:
            if any(kw in trimmed.lower() for kw in ("rls mapping", "row-level security", "rls security", "security & data filtering")):
                flush_block()
                in_rls_section = True
                continue

            # Check single-line bullet with colon: "- table: WHERE ..." or "table: WHERE ..."
            bullet_match = re.match(r"^[-*]?\s*[`]?([a-zA-Z_][a-zA-Z0-9_]*)[`]?\s*:\s*(.+)$", trimmed)
            if bullet_match:
                tbl = bullet_match.group(1).lower()
                rest = bullet_match.group(2).strip()
                if "where" in rest.lower() or "join" in rest.lower():
                    flush_block()
                    parsed = cls._parse_sql_expression(tbl, rest)
                    if parsed:
                        raw_rules.append(parsed)
                    continue

            # Check table header line: "table:" or "- table:"
            table_header_match = re.match(r"^[-*]?\s*[`]?([a-zA-Z_][a-zA-Z0-9_]*)[`]?\s*:$", trimmed)
            if table_header_match:
                tbl = table_header_match.group(1).lower()
                if tbl not in ("note", "important", "warning", "tip", "where", "select", "join", "filter", "rules"):
                    flush_block()
                    current_table = tbl
                    continue

            # Accumulate SQL lines for current table block
            if current_table:
                current_sql_lines.append(trimmed)

        flush_block()
        return raw_rules

    @classmethod
    def _parse_sql_expression(
        cls, target_table: str, sql_expression: str, join_logic: str = ""
    ) -> dict[str, Any] | None:
        """Parse SQL fragment into predicate, parameter, and joins."""
        clean_sql = sql_expression.strip().strip("`").strip(";")
        if not clean_sql:
            return None

        where_match = re.search(r"\bWHERE\b\s+(.*)", clean_sql, re.IGNORECASE)
        if not where_match:
            return None

        predicate = where_match.group(1).strip().strip(";").strip()
        # Extract parameter token: e.g. @UserBranchId
        param_match = re.search(r"@\w+", predicate)
        if not param_match:
            param_match = re.search(r"@\w+", clean_sql)
        param = param_match.group(0) if param_match else None

        # Parse joins before WHERE
        pre_where = clean_sql[:where_match.start()].strip()
        join_matches = re.findall(
            r"(?:(INNER|LEFT|RIGHT|FULL)\s+)?JOIN\s+[`]?(\w+)[`]?(?:\s+(?:AS\s+)?([`]?\w+[`]?))?\s+ON\s+([^;\n]+?)(?=(?:(?:INNER|LEFT|RIGHT|FULL)\s+)?JOIN|\s*$)",
            pre_where,
            re.IGNORECASE
        )

        joins: list[dict[str, Any]] = []
        for j_type, j_tbl, j_alias, j_on in join_matches:
            join_type = j_type.upper() if j_type else "INNER"
            joins.append({
                "join_type": f"{join_type} JOIN",
                "table": j_tbl.lower().strip("`"),
                "alias": j_alias.strip("`") if j_alias else None,
                "condition": j_on.strip()
            })

        path_segments: list[str] = []
        for j in joins:
            cond = j["condition"]
            path_segments.append(cond)
        path_segments.append(predicate)
        path_str = " -> ".join(path_segments)

        is_direct = (len(joins) == 0) or ("directly" in join_logic.lower())

        return {
            "target_table": target_table.lower(),
            "predicate": predicate,
            "parameter": param,
            "joins": joins,
            "path": path_str,
            "raw_sql": clean_sql,
            "join_logic": join_logic,
            "is_direct": is_direct,
        }

    @classmethod
    def _group_into_domains(cls, raw_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Group parsed table rules into structured security domains."""
        by_param: dict[str, list[dict[str, Any]]] = {}
        for r in raw_rules:
            p = r["parameter"] or "unknown"
            by_param.setdefault(p, []).append(r)

        domains: list[dict[str, Any]] = []

        for param, rules in by_param.items():
            pred_col_counts: Counter[str] = Counter()
            direct_roots: list[str] = []

            for r in rules:
                pred = r["predicate"]
                col_match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*(=|<|>|IN)", pred)
                if col_match:
                    tbl, col = col_match.group(1).lower(), col_match.group(2).lower()
                    pred_col_counts[f"{tbl}.{col}"] += 1
                    if r["is_direct"] and r["target_table"] == tbl:
                        direct_roots.append(f"{tbl}.{col}")

            canonical_root: str = ""
            if direct_roots:
                canonical_root = max(direct_roots, key=lambda root: pred_col_counts[root])
            elif pred_col_counts:
                canonical_root = pred_col_counts.most_common(1)[0][0]
            else:
                first_tbl = rules[0]["target_table"]
                canonical_root = f"{first_tbl}.id"

            root_table, root_col = canonical_root.split(".", 1) if "." in canonical_root else (canonical_root, "id")

            scope_name = "security"
            if param and param.startswith("@"):
                raw_param_name = param[1:]
                for prefix in ("User", "Current", "Auth", "Session"):
                    if raw_param_name.startswith(prefix):
                        raw_param_name = raw_param_name[len(prefix):]
                        break
                if raw_param_name.endswith("Id") and len(raw_param_name) > 2:
                    raw_param_name = raw_param_name[:-2]
                scope_name = raw_param_name.lower()
            elif root_col.endswith("_id") and len(root_col) > 3:
                scope_name = root_col[:-3]

            canonical_predicate = f"{canonical_root} = {param}" if param else f"{canonical_root} IS NOT NULL"

            for r in rules:
                if r["target_table"] == root_table and r["is_direct"]:
                    canonical_predicate = r["predicate"]
                    break

            propagation_paths: list[dict[str, Any]] = []
            for r in rules:
                tbl = r["target_table"]
                is_root = (tbl == root_table and r["is_direct"])
                
                is_direct_root_or_peer = is_root or (r["is_direct"] and tbl in (root_table, "branches", "accounts"))
                pred_eq = {
                    "INNER JOIN": True if is_direct_root_or_peer else False,
                    "LEFT JOIN": "conditional" if is_direct_root_or_peer else False,
                    "RIGHT JOIN": "conditional" if is_direct_root_or_peer else False,
                    "FULL JOIN": False,
                }

                propagation_paths.append({
                    "target_table": tbl,
                    "path": r["path"],
                    "predicate": r["predicate"],
                    "propagation": "allowed",
                    "is_canonical_root": is_root,
                    "predicate_equivalence": pred_eq,
                    "joins": r["joins"],
                    "source_sql": r["raw_sql"]
                })

            domain = {
                "name": scope_name,
                "security_scope": scope_name,
                "canonical_root": canonical_root,
                "canonical_predicate": canonical_predicate,
                "security_parameter": param,
                "description": f"{scope_name.capitalize()}-level row security scope with canonical root {canonical_root}.",
                "source": "documentation",
                "authoritative": True,
                "propagation_paths": propagation_paths,
            }
            domains.append(domain)

        return domains
