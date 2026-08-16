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

        response = self._llm_client.generate(GenerationRequest(prompt=prompt))

        return self._parse(response.text)

    @staticmethod
    def _parse(text: str) -> CriticResult:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            # A malformed critic response must never crash or block a SQL
            # query that already passed deterministic validation. Treat it
            # as PASS (see SelfCorrectionService for the rationale).
            return CriticResult(status="PASS", issues=())

        status = payload.get("status")
        if status not in {"PASS", "FAIL", "UNKNOWN"}:
            return CriticResult(status="PASS", issues=())

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
