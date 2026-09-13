"""Adapter to translate Backend RLS Policy JSON into Semantic Layer security_domains.

The Backend exposes an authoritative RLS policy endpoint:
    GET /api/v1/semantic-layer/{layerId}/rls-policy
returning a structured JSON contract (RlsPolicyRequest):
    {
        "enabled": true,
        "userValueField": "BranchId",
        "scopeParameter": "@UserScopeId",
        "rules": [
            {
                "table": "accounts",
                "scopeColumn": "branch_id",
                "type": "direct"
            },
            {
                "table": "customers",
                "joinTable": "accounts",
                "joinFromColumn": "customer_id",
                "joinToColumn": "customer_id",
                "scopeColumn": "branch_id",
                "type": "join"
            }
        ]
    }

This adapter transforms this into the canonical `security_domains` structure
enforced by SemanticLayerValidator and SQLRlsValidator.
"""

from __future__ import annotations

import json
from typing import Any
from collections import Counter


class RlsPolicyAdapter:
    """Transforms Backend RlsPolicyRequest contracts into Semantic Layer security_domains."""

    @classmethod
    def to_security_domains(
        cls,
        backend_policy: dict[str, Any] | str | None,
    ) -> list[dict[str, Any]]:
        """Convert a backend RLS policy into a list of canonical security domains.

        Args:
            backend_policy: Dict or JSON string from Backend RLS policy endpoint.

        Returns:
            List of normalized security domain objects adhering to the Semantic Layer schema.
        """
        if backend_policy is None:
            return []

        if isinstance(backend_policy, str):
            clean = backend_policy.strip()
            if not clean:
                return []
            try:
                backend_policy = json.loads(clean)
            except Exception:
                return []

        if not isinstance(backend_policy, dict):
            return []

        # Check if enabled
        enabled = backend_policy.get("enabled", True)
        if enabled is False:
            return []

        rules = backend_policy.get("rules", [])
        if not isinstance(rules, list) or not rules:
            return []

        # Extract valid rule dicts first to enable dynamic inference if needed
        valid_rules: list[dict[str, Any]] = [
            r for r in rules if isinstance(r, dict) and r.get("table") and (r.get("scopeColumn") or r.get("scope_column"))
        ]
        if not valid_rules:
            return []

        # Determine domain/scope name dynamically from userValueField or first rule's scopeColumn
        user_field = backend_policy.get("userValueField") or backend_policy.get("user_value_field")
        domain_name = ""
        if isinstance(user_field, str) and user_field.strip():
            raw_field = user_field.strip()
            if raw_field.endswith("Id") and len(raw_field) > 2:
                domain_name = raw_field[:-2].lower()
            else:
                domain_name = raw_field.lower()
        else:
            first_col = str(valid_rules[0].get("scopeColumn") or valid_rules[0].get("scope_column") or "").strip().lower()
            if first_col.endswith("_id") and len(first_col) > 3:
                domain_name = first_col[:-3]
            elif first_col:
                domain_name = first_col
            else:
                domain_name = "branch"

        # Extract and format scope parameter (e.g. @UserBranchId, @UserStoreId)
        raw_param = backend_policy.get("scopeParameter") or backend_policy.get("scope_parameter")
        if isinstance(raw_param, str) and raw_param.strip():
            param = raw_param.strip()
            if not param.startswith("@"):
                param = f"@{param}"
        else:
            param = f"@User{domain_name.capitalize()}Id" if domain_name else "@UserScopeId"

        # Optional branch/scope mapping from backend contract
        branch_mapping = (
            backend_policy.get("branchMapping")
            or backend_policy.get("branch_mapping")
            or backend_policy.get("scopeMapping")
            or backend_policy.get("scope_mapping")
        )

        # Find direct rules (no joinTable or joinTable == table or type == direct)
        direct_rules = [
            r for r in valid_rules
            if str(r.get("type", "")).lower() == "direct"
            or not r.get("joinTable")
            or str(r.get("joinTable", "")).strip().lower() == str(r.get("table", "")).strip().lower()
        ]

        # Identify join targets that reference direct tables as joinTable
        join_references: Counter[str] = Counter()
        for r in valid_rules:
            jt = r.get("joinTable")
            if jt and isinstance(jt, str):
                join_references[jt.strip().lower()] += 1

        # Select canonical root
        canonical_root_table = ""
        canonical_root_col = ""

        if direct_rules:
            # Pick the direct table most referenced by joins, or first direct table
            best_direct = max(
                direct_rules,
                key=lambda r: join_references[str(r.get("table", "")).strip().lower()],
            )
            canonical_root_table = str(best_direct["table"]).strip().lower()
            canonical_root_col = str(best_direct["scopeColumn"]).strip().lower()
        else:
            # Fallback to first rule
            canonical_root_table = str(valid_rules[0]["table"]).strip().lower()
            canonical_root_col = str(valid_rules[0]["scopeColumn"]).strip().lower()

        canonical_root = f"{canonical_root_table}.{canonical_root_col}"
        canonical_predicate = f"{canonical_root} = {param}"

        # Direct table set for equivalence checks
        direct_tables = {
            str(r["table"]).strip().lower() for r in direct_rules
        }
        direct_tables.add(canonical_root_table)

        # Build propagation paths
        propagation_paths: list[dict[str, Any]] = []

        for r in valid_rules:
            tbl = str(r["table"]).strip().lower()
            scope_col = str(r.get("scopeColumn", canonical_root_col)).strip().lower()
            jt_raw = r.get("joinTable")
            join_tbl = str(jt_raw).strip().lower() if jt_raw and str(jt_raw).strip() else None
            is_direct = (
                str(r.get("type", "")).lower() == "direct"
                or not join_tbl
                or join_tbl == tbl
            )

            is_root = (tbl == canonical_root_table and is_direct)
            is_peer_or_root = tbl in direct_tables and is_direct

            pred_eq = {
                "INNER JOIN": True if is_peer_or_root else False,
                "LEFT JOIN": "conditional" if is_peer_or_root else False,
                "RIGHT JOIN": "conditional" if is_peer_or_root else False,
                "FULL JOIN": False,
            }

            if is_direct:
                path_str = f"{tbl}.{scope_col} = {param}"
                pred_str = f"{tbl}.{scope_col} = {param}"
                joins_list: list[dict[str, Any]] = []
                raw_sql = f"WHERE {pred_str}"
            else:
                from_col = str(r.get("joinFromColumn", "")).strip().lower()
                to_col = str(r.get("joinToColumn", "")).strip().lower()

                # Build canonical arrow path
                path_str = f"{tbl}.{from_col} = {join_tbl}.{to_col} -> {join_tbl}.{scope_col} = {param}"
                pred_str = f"{join_tbl}.{scope_col} = {param}"
                condition_str = f"{tbl}.{from_col} = {join_tbl}.{to_col}"
                joins_list = [
                    {
                        "join_type": "INNER JOIN",
                        "table": join_tbl,
                        "alias": None,
                        "condition": condition_str,
                    }
                ]
                raw_sql = f"INNER JOIN {join_tbl} ON {condition_str} WHERE {pred_str}"

            propagation_paths.append({
                "target_table": tbl,
                "path": path_str,
                "predicate": pred_str,
                "propagation": "allowed",
                "is_canonical_root": is_root,
                "predicate_equivalence": pred_eq,
                "joins": joins_list,
                "source_sql": raw_sql,
            })

        domain = {
            "name": domain_name,
            "security_scope": domain_name,
            "canonical_root": canonical_root,
            "canonical_predicate": canonical_predicate,
            "security_parameter": param,
            "description": f"{domain_name.capitalize()}-level row security scope with canonical root {canonical_root}.",
            "source": "backend_policy",
            "authoritative": True,
            "propagation_paths": propagation_paths,
        }

        if branch_mapping:
            domain["branch_mapping"] = branch_mapping
            domain["scope_mapping"] = branch_mapping

        return [domain]
