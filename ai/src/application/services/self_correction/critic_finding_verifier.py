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


class CriticFindingVerifier:
    """Deterministic verifier that grounds LLM critic findings in physical schema reality.

    Inspects `table.column` references cited as evidence by the SQL Critic LLM. If the
    cited elements do not exist in the physical schema, the finding is discarded as an LLM
    hallucination rather than triggering an invalid correction attempt.
    """

    def __init__(self, schema_provider: PhysicalSchemaRepository) -> None:
        """Initialize the critic finding verifier.

        Args:
            schema_provider: Physical schema repository for grounding checks.
        """
        self._schema_provider = schema_provider

    def verify(self, critic_result: CriticResult, schema: dict[str, Any] | None = None) -> list[ValidationIssue]:
        """Filter and verify critic issues against the authoritative physical schema.

        Args:
            critic_result: Output from SQLCriticService.
            schema: Optional pre-loaded physical schema dictionary.

        Returns:
            List of verified ValidationIssue objects grounded in schema evidence or intent rules.
        """
        if critic_result.status != "FAIL":
            # PASS -> nothing to verify. UNKNOWN -> insufficient context to
            # judge; per the "never guess" rule, this is not treated as a
            # confirmed problem, so SQL that already passed deterministic
            # validation is not blocked on an unresolved critic finding.
            return []

        tables = (schema or self._schema_provider.get_schema())["tables"]
        verified: list[ValidationIssue] = []

        for issue in critic_result.issues:
            reference_text = f"{issue.evidence or ''} {issue.description}"
            references = _TABLE_COLUMN_PATTERN.findall(reference_text)

            if not references:
                # No checkable table.column reference: this is an
                # intent-level judgment (e.g. "missing a date filter"),
                # which deterministic validators cannot evaluate. Trust it.
                verified.append(
                    ValidationIssue(
                        type=issue.type,
                        message=issue.description,
                        source=_SOURCE,
                    )
                )
                continue

            if self._all_references_grounded(references, tables):
                verified.append(
                    ValidationIssue(
                        type=issue.type,
                        message=issue.description,
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

            known_columns = {col["name"] for col in table["columns"]}
            if column_name not in known_columns:
                return False

        return True
