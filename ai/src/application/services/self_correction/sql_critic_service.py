"""Application service for the SQL Critic step.

Reuses the existing LLMClient port and GenerationRequest/GenerationResponse
DTOs -- no new request/response types are introduced for this LLM call,
only a dedicated prompt and a dedicated (small) parser for its JSON output.
"""

from __future__ import annotations

import json

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.ports.llm_client import LLMClient
from src.application.dto.self_correction.critic_result import CriticIssue, CriticResult
from src.prompts.sql_critic_prompt import SQL_CRITIC_PROMPT


class SQLCriticService:
    """Judges whether a validated SQL query answers the user's question.

    The critic never returns SQL and is never trusted on its own --
    its findings are only advisory input to CriticFindingVerifier.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def evaluate(self, question: str, sql: str, semantic_context: str) -> CriticResult:
        prompt = SQL_CRITIC_PROMPT.format(
            question=question,
            sql=sql,
            semantic_context=semantic_context,
        )

        try:
            response = self._llm_client.generate(GenerationRequest(prompt=prompt))
        except Exception as exc:
            return CriticResult(status="FAIL", issues=(CriticIssue(
                type="CRITIC_UNAVAILABLE",
                description=f"SQL critic could not evaluate the candidate: {type(exc).__name__}.",
            ),))
        return self._parse(response.text)

    @staticmethod
    def _parse(text: str) -> CriticResult:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            # The critic is advisory. A malformed critic answer must not
            # reject SQL that already passed deterministic safety checks.
            return CriticResult(status="UNKNOWN", issues=(CriticIssue(
                type="CRITIC_MALFORMED_RESPONSE",
                description="SQL critic returned malformed JSON.",
            ),))

        status = payload.get("status")
        if status not in {"PASS", "FAIL", "UNKNOWN"}:
            return CriticResult(status="UNKNOWN", issues=(CriticIssue(
                type="CRITIC_INVALID_RESPONSE",
                description="SQL critic returned an unsupported status.",
            ),))

        if status == "UNKNOWN":
            # UNKNOWN is not a confirmed defect. The deterministic validators
            # already enforce syntax, schema, relationship, and RLS safety.
            return CriticResult(status="UNKNOWN", issues=(CriticIssue(
                type="CRITIC_UNKNOWN",
                description="SQL critic could not determine whether the SQL answers the request.",
            ),))

        raw_issues = payload.get("issues") or []
        issues = tuple(
            CriticIssue(
                type=str(issue.get("type", "UNSPECIFIED")),
                description=str(issue.get("description", "")),
                evidence=issue.get("evidence"),
            )
            for issue in raw_issues
            if isinstance(issue, dict) and issue.get("description")
        )

        return CriticResult(status=status, issues=issues)
