"""Application service for the SQL Correction step.

Reuses the existing LLMClient port and GenerationRequest/GenerationResponse
DTOs, exactly like SQLGenerationService and SQLCriticService -- no new
LLM-call abstraction is introduced. Each call builds a fresh, self-
contained prompt from ValidationIssue objects; it never continues a
previous conversation.
"""

from __future__ import annotations

import re
from typing import Any

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.ports.llm_client import LLMClient
from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.prompts.sql_correction_prompt import SQL_CORRECTION_PROMPT


class SQLCorrectionService:
    """Produces a corrected SQL statement that fixes only the given issues."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def correct(
        self,
        question: str,
        current_sql: str,
        issues: list[ValidationIssue],
        relevant_schema: dict[str, Any],
        relevant_relationships: list[dict[str, Any]],
    ) -> str | None:
        deterministic = self._deterministic_rls_correction(current_sql, issues)
        if deterministic is not None:
            return deterministic

        prompt = SQL_CORRECTION_PROMPT.format(
            question=question,
            current_sql=current_sql,
            issues=self._render_issues(issues),
            relevant_schema=self._render_schema(relevant_schema),
            relevant_relationships=self._render_relationships(relevant_relationships),
        )

        response = self._llm_client.generate(GenerationRequest(prompt=prompt))

        return self._extract_sql(response.text)

    @staticmethod
    def _deterministic_rls_correction(
        current_sql: str,
        issues: list[ValidationIssue],
    ) -> str | None:
        """Repair the mandatory banking RLS shape without another model call.

        RLS is a backend security contract, so the required loans path is
        deterministic. This fallback prevents a local model from repeating
        an invalid query or returning prose during the correction loop.
        """
        if not any(issue.type == "rls" for issue in issues):
            return None

        if not re.search(r"\bFROM\s+(?:[\w]+\.)?loans\b", current_sql, re.IGNORECASE):
            return None

        if re.search(r"\bJOIN\s+customers\b", current_sql, re.IGNORECASE):
            return None

        from_match = re.search(
            r"\bFROM\s+((?:[\w]+\.)?loans)"
            r"(?:\s+(?:AS\s+)?([A-Za-z_]\w*))?",
            current_sql,
            re.IGNORECASE,
        )
        if from_match is None:
            return None

        table_ref = from_match.group(1)
        alias = from_match.group(2)
        if alias and alias.upper() in {
            "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "JOIN", "WHERE",
            "GROUP", "ORDER", "HAVING", "LIMIT", "OFFSET",
        }:
            alias = None
        loan_ref = alias or table_ref
        joins = (
            f" INNER JOIN customers AS c ON {loan_ref}.customer_id = c.customer_id"
            " INNER JOIN accounts AS a ON c.customer_id = a.customer_id"
            " INNER JOIN branches AS b ON a.branch_id = b.branch_id "
        )

        clause = re.search(
            r"\b(WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|OFFSET)\b",
            current_sql[from_match.end():],
            re.IGNORECASE,
        )
        insert_at = from_match.end() + clause.start() if clause else len(current_sql)
        corrected = current_sql[:insert_at] + joins + current_sql[insert_at:]

        where_match = re.search(r"\bWHERE\b", corrected, re.IGNORECASE)
        branch_filter = "b.branch_id = @UserBranchId"
        if where_match:
            tail = corrected[where_match.end():]
            boundary = re.search(
                r"\b(GROUP\s+BY|HAVING|ORDER\s+BY|OFFSET)\b",
                tail,
                re.IGNORECASE,
            )
            condition = tail[:boundary.start()] if boundary else tail
            suffix = tail[boundary.start():] if boundary else ""
            corrected = (
                corrected[:where_match.end()]
                + f" {branch_filter} AND ({condition.strip()})"
                + suffix
            )
        else:
            boundary = re.search(
                r"\b(GROUP\s+BY|HAVING|ORDER\s+BY|OFFSET)\b",
                corrected[insert_at:],
                re.IGNORECASE,
            )
            at = insert_at + boundary.start() if boundary else len(corrected)
            corrected = corrected[:at] + f" WHERE {branch_filter} " + corrected[at:]

        return corrected.strip()

    @staticmethod
    def _render_issues(issues: list[ValidationIssue]) -> str:
        return "\n".join(f"- [{issue.type}] {issue.message}" for issue in issues)

    @staticmethod
    def _render_schema(relevant_schema: dict[str, Any]) -> str:
        if not relevant_schema:
            return "(no relevant tables resolved)"

        lines = []
        for table_name, table in sorted(relevant_schema.items()):
            columns = ", ".join(col["name"] for col in table.get("columns", []))
            lines.append(f"{table_name}: {columns}")
        return "\n".join(lines)

    @staticmethod
    def _render_relationships(relationships: list[dict[str, Any]]) -> str:
        if not relationships:
            return "(no relevant relationships resolved)"

        lines = [
            f"{rel['from_table']}.{rel['from_column']} -> {rel['to_table']}.{rel['to_column']}"
            for rel in relationships
        ]
        return "\n".join(lines)

    @staticmethod
    def _extract_sql(text: str) -> str | None:
        cleaned = text.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("sql"):
                cleaned = cleaned[3:]
            cleaned = cleaned.strip()

        return cleaned or None
