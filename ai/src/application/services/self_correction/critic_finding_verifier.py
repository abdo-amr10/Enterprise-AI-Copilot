"""Deterministic verification of SQL Critic findings.

This is the component that prevents critic hallucination from turning
into a correction. Any `table.column` reference the critic cites as
evidence is checked against the physical schema; a finding whose
evidence does not exist is discarded rather than acted on. Findings
that make a pure intent-level judgment (no specific table/column
reference to check) are passed through, since that judgment call is
exactly the class of problem deterministic validators cannot make.
"""

from __future__ import annotations

import re
from typing import Any

from src.application.dto.self_correction.critic_result import CriticResult
from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.application.ports.physical_schema_repository import PhysicalSchemaRepository

_SOURCE = "critic"
_TABLE_COLUMN_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")

# Regex to detect Critic claims that attempt to strip DISTINCT
_ANTI_DISTINCT_PATTERN = re.compile(
    r"\b(?:remove\s+distinct|unnecessary\s+distinct|extra\s+distinct|do\s+not\s+(?:use|need)\s+distinct)\b",
    re.IGNORECASE,
)

# Regex to detect Critic claims that a condition/filter is missing
_MISSING_FILTER_PATTERN = re.compile(
    r"\b(?:does\s+not\s+filter|missing\s+(?:a\s+)?filter|missing\s+(?:a\s+)?condition|no\s+filter)\b",
    re.IGNORECASE,
)
_MISSING_JOIN_PATTERN = re.compile(
    r"\b(?:does\s+not\s+join|missing\s+(?:a\s+)?join|no\s+join|not\s+joined|does\s+not\s+include\s+(?:a\s+)?join)\b",
    re.IGNORECASE,
)
_QUOTED_IDENTIFIER_PATTERN = re.compile(r"['\"`]([A-Za-z0-9_]+)['\"`]")
_NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")


class CriticFindingVerifier:
    """Deterministic verifier that grounds LLM critic findings in physical schema reality and security policy.

    Inspects `table.column` references cited as evidence by the SQL Critic LLM. If the
    cited elements do not exist in the physical schema, or if the finding objects to mandatory
    security rules declared in semantic metadata, or if the finding objects to legitimate DISTINCT/fanout
    protections, or if the finding falsely claims a condition is missing when it already exists
    in the SQL, the finding is discarded as an LLM hallucination rather than triggering an invalid
    correction attempt.
    """

    def __init__(
        self,
        schema_provider: PhysicalSchemaRepository,
        semantic_repository: Any = None,
    ) -> None:
        """Initialize the critic finding verifier.

        Args:
            schema_provider: Physical schema repository for grounding checks.
            semantic_repository: Optional semantic repository for active security domain metadata.
        """
        self._schema_provider = schema_provider
        self._semantic_repository = semantic_repository

    def _get_security_parameters(self) -> set[str]:
        """Extract active security parameter names (e.g. {'@userbranchid', '@tenantid'})."""
        params: set[str] = set()
        if self._semantic_repository is not None:
            try:
                layer = self._semantic_repository.load()
                if isinstance(layer, dict):
                    domains = layer.get("security_domains", [])
                    for domain in domains:
                        if isinstance(domain, dict):
                            pred = domain.get("canonical_predicate", "")
                            for m in re.finditer(r"@\w+", pred):
                                params.add(m.group(0).casefold())
            except Exception:
                pass
        return params

    def verify(
        self,
        critic_result: CriticResult,
        schema: dict[str, Any] | None = None,
        sql: str | None = None,
    ) -> list[ValidationIssue]:
        """Filter and verify critic issues against authoritative schema, SQL reality, and security policy.

        Args:
            critic_result: Output from SQLCriticService.
            schema: Optional pre-loaded physical schema dictionary.
            sql: Optional candidate SQL string under review.

        Returns:
            List of verified ValidationIssue objects grounded in schema evidence or intent rules.
        """
        if critic_result.status != "FAIL":
            return []

        tables = (schema or self._schema_provider.get_schema())["tables"]
        verified: list[ValidationIssue] = []
        security_params = self._get_security_parameters()
        anti_intent_terms = ("not mentioned", "not requested", "did not ask", "did not mention", "unnecessary", "extra")

        for issue in critic_result.issues:
            description = issue.description or ""
            evidence = issue.evidence or ""
            reference_text = f"{evidence} {description}"
            ref_lower = reference_text.casefold()

            # 1. Reject any finding that objects to mandatory security domain parameters or RLS scope boundaries
            if security_params:
                if any(param in ref_lower for param in security_params):
                    continue
                if any(term in ref_lower for term in (
                    "specific branch", "single branch", "user branch", "branch restriction",
                    "only shows branch", "identified by @", "restricted to @", "filtered by @"
                )):
                    continue

            # 2. Reject any finding that objects to DISTINCT semantics
            if _ANTI_DISTINCT_PATTERN.search(reference_text):
                continue

            # 3. Check if the finding falsely claims a filter or security condition is missing when SQL has it
            target_sql = sql or (evidence if "select" in evidence.casefold() else None)
            if target_sql:
                target_sql_lower = target_sql.casefold()
                if _MISSING_FILTER_PATTERN.search(reference_text):
                    if security_params:
                        has_security_term = any(param in ref_lower for param in security_params) or any(
                            term in ref_lower for term in ("branch", "branch_id", "branch id", "user's branch", "user branch")
                        )
                        if has_security_term and any(param in target_sql_lower for param in security_params):
                            continue
                    numbers = _NUMBER_PATTERN.findall(description)
                    if numbers and all(num in target_sql for num in numbers):
                        continue

                # 4. Check if the finding falsely claims a join/table/CTE is missing when SQL already contains/joins it
                if _MISSING_JOIN_PATTERN.search(reference_text):
                    quoted = _QUOTED_IDENTIFIER_PATTERN.findall(reference_text)
                    cte_names = [m.group(1).casefold() for m in re.finditer(r"\b([A-Za-z0-9_]+)\s+AS\s*\(", target_sql, re.IGNORECASE)]
                    all_candidates = set(q.casefold() for q in quoted)
                    for t_name in tables.keys():
                        if t_name.casefold() in ref_lower:
                            all_candidates.add(t_name.casefold())
                    for c_name in cte_names:
                        if c_name in ref_lower:
                            all_candidates.add(c_name)

                    if all_candidates and all(cand in target_sql_lower for cand in all_candidates):
                        continue

            references = _TABLE_COLUMN_PATTERN.findall(reference_text)

            if not references:
                # No checkable table.column reference: this is an
                # intent-level judgment (e.g. "missing a date filter"),
                # which deterministic validators cannot evaluate. Trust it as long
                # as it does not violate mandatory security constraints.
                verified.append(
                    ValidationIssue(
                        type=issue.type,
                        message=description,
                        source=_SOURCE,
                    )
                )
                continue

            if self._all_references_grounded(references, tables):
                verified.append(
                    ValidationIssue(
                        type=issue.type,
                        message=description,
                        source=_SOURCE,
                    )
                )
            # else: the critic cited a table/column that does not exist --
            # this finding is a hallucination and is silently discarded.

        return verified

    @staticmethod
    def _all_references_grounded(
        references: list[tuple[str, str]],
        tables: dict,
    ) -> bool:
        for table_name, column_name in references:
            table = tables.get(table_name)
            if table is None:
                return False

            known_columns = {col["name"] for col in table.get("columns", [])}
            if column_name not in known_columns:
                return False

        return True
