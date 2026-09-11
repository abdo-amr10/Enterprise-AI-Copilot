"""Application service for the SQL Correction step.

Reuses the existing LLMClient port and GenerationRequest/GenerationResponse
DTOs, exactly like SQLGenerationService and SQLCriticService -- no new
LLM-call abstraction is introduced. Each call builds a fresh, self-
contained prompt from ValidationIssue objects; it never continues a
previous conversation.
"""

from __future__ import annotations

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
        rejected_candidates: list[tuple[str, list[ValidationIssue]]] | None = None,
    ) -> str | None:
        prompt = SQL_CORRECTION_PROMPT.format(
            question=question,
            current_sql=current_sql,
            issues=self._render_issues(issues),
            relevant_schema=self._render_schema(relevant_schema),
            relevant_relationships=self._render_relationships(relevant_relationships),
            rejected_candidates=self._render_rejected_candidates(rejected_candidates),
        )

        try:
            from src.observability.latency_audit import record_prompt
            record_prompt(
                stage_name="sql_correction_prompt",
                model="qwen2.5-coder:7b",
                config_name="sql_correction",
                prompt=prompt,
                components={
                    "question_chars": len(question),
                    "current_sql_chars": len(current_sql),
                    "issues_count": len(issues),
                },
            )
        except Exception:
            pass

        try:
            from src.observability.latency_audit import stage as audit_stage
            with audit_stage("sql_correction_llm", is_leaf=True):
                response = self._llm_client.generate(GenerationRequest(prompt=prompt))
        except Exception:
            response = self._llm_client.generate(GenerationRequest(prompt=prompt))

        return self._extract_sql(response.text)

    @staticmethod
    def _render_rejected_candidates(
        rejected_candidates: list[tuple[str, list[ValidationIssue]]] | None,
    ) -> str:
        if not rejected_candidates:
            return "(no previous candidates rejected in this run)"

        blocks = []
        for idx, (cand_sql, cand_issues) in enumerate(rejected_candidates, 1):
            issue_lines = "\n".join(f"  - [{issue.type}] {issue.message}" for issue in cand_issues)
            blocks.append(
                f"Candidate #{idx}:\n"
                f"{cand_sql.strip()}\n"
                f"Issues that caused rejection:\n{issue_lines if issue_lines else '  - (unspecified issue)'}"
            )
        return "\n\n".join(blocks)

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
            if all(
                isinstance(rel.get(field), str) and rel[field]
                for field in ("from_table", "from_column", "to_table", "to_column")
            )
        ]
        return "\n".join(lines) or "(no complete relationships resolved)"

    @staticmethod
    def _extract_sql(text: str) -> str | None:
        cleaned = text.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("sql"):
                cleaned = cleaned[3:]
            cleaned = cleaned.strip()

        return cleaned or None
