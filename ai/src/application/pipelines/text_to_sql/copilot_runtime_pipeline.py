"""Translate a Copilot question into safe, backend-executable read-only SQL."""

from __future__ import annotations

import json
import re
import logging
from collections.abc import Callable
from typing import Any

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.backend.copilot.text_to_sql_runtime_response import (
    TextToSQLRuntimeResponse,
)
from src.application.services.self_correction.self_correction_service import (
    SelfCorrectionService,
)
from src.application.services.text_to_sql.text_to_sql_pipeline import TextToSQLPipeline

logger = logging.getLogger(__name__)

class CopilotRuntimePipeline:
    """AI-owned portion of `POST /api/v1/copilot/ask`.

    This pipeline never executes SQL. The Backend remains responsible for
    authorization, RLS, SQL Server execution, result formatting, and history.
    """
    
    @staticmethod
    def _parse_generation_response(text: str) -> dict:
        cleaned = text.strip()

        # Remove Markdown code fences if the model wraps JSON in them.
        if cleaned.startswith("```") and cleaned.endswith("```"):
            lines = cleaned.splitlines()

            # Remove opening fence: ```json / ```
            lines = lines[1:]

            # Remove closing fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            cleaned = "\n".join(lines).strip()

        payload = json.loads(cleaned)

        if not isinstance(payload, dict):
            raise ValueError("LLM response must be a JSON object.")

        return payload

    _FORBIDDEN_SQL = re.compile(
        r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|"
        r"EXEC(?:UTE)?|SELECT\s+INTO|USE|GRANT|REVOKE|DENY|DBCC|BACKUP|RESTORE)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        text_to_sql_pipeline: TextToSQLPipeline,
        self_correction_service: SelfCorrectionService,
    ) -> None:
        self._text_to_sql_pipeline = text_to_sql_pipeline
        self._self_correction_service = self_correction_service

    def run(
        self,
        request: CopilotAskRequest,
        trace_observer: Callable[[dict[str, Any]], None] | None = None,
    ) -> TextToSQLRuntimeResponse:
        try:
            semantic_context = self._text_to_sql_pipeline.build_context(request.question)
            generated = self._text_to_sql_pipeline.run(
                question=request.question,
                semantic_context=semantic_context,
            )
        except Exception as exc:
            logger.exception("Text-to-SQL generation failed")
            return TextToSQLRuntimeResponse.failure(
                "SQL_GENERATION_FAILED",
                "The system could not generate SQL for this request.",
                failure_reason=f"Generation service failed: {type(exc).__name__}.",
            )
        try:
            payload = self._parse_generation_response(generated.text)
        except (json.JSONDecodeError, ValueError):
            logger.info("Generated model output was not a valid structured response")
            return TextToSQLRuntimeResponse.failure(
                "SQL_VALIDATION_FAILED",
                "The model response was not a valid structured SQL result.",
                failure_reason="The generation model did not return the required JSON SQL contract.",
            )

        if payload.get("status") != "success":
            warnings = payload.get("warnings")
            reason = "; ".join(str(item) for item in warnings) if isinstance(warnings, list) else None
            logger.info("Generated model output requested clarification")
            return TextToSQLRuntimeResponse.failure(
                "SQL_NEEDS_CLARIFICATION",
                "The request cannot be translated into a safe query without more information.",
                failure_reason=reason or "The model did not identify a safe, supported query.",
            )

        sql = payload.get("sql")
        if (
            not isinstance(sql, str)
            or not sql.strip()
            or payload.get("is_read_only") is not True
            or self._FORBIDDEN_SQL.search(sql)
        ):
            logger.info("Generated model output was unsafe or incomplete")
            return TextToSQLRuntimeResponse.failure(
                "SQL_VALIDATION_FAILED",
                "The system could not generate a safe read-only query for this request.",
                failure_reason=(
                    "The generated payload was missing SQL, was not marked read-only, "
                    "or contained a forbidden write/administrative operation."
                ),
            )

        sql = sql.strip()
        self._notify_trace_observer(
            trace_observer,
            {"event": "initial_generation", "sql": sql},
        )

        try:
            correction_kwargs: dict[str, Any] = {
                "question": request.question,
                "sql": sql,
                "semantic_context": semantic_context,
            }
            if trace_observer is not None:
                correction_kwargs["trace_observer"] = trace_observer
            outcome = self._self_correction_service.run(**correction_kwargs)
        except Exception as exc:
            logger.exception("Text-to-SQL validation/correction failed")
            return TextToSQLRuntimeResponse.failure(
                "SQL_VALIDATION_FAILED",
                "The system could not validate the generated SQL.",
                failure_reason=f"Validation service failed: {type(exc).__name__}.",
            )

        if not outcome.is_valid:
            self._notify_trace_observer(
                trace_observer,
                {
                    "event": "final_result",
                    "sql": None,
                    "attemptsUsed": outcome.attempts_used,
                    "status": "failed",
                    "issues": list(outcome.issues),
                },
            )
            return TextToSQLRuntimeResponse.failure(
                "MAX_RETRIES_EXCEEDED",
                "The system could not generate a valid read-only SQL query.",
                failure_reason="; ".join(outcome.issues) or "The query remained invalid after correction attempts.",
            )

        self._notify_trace_observer(
            trace_observer,
            {
                "event": "final_result",
                "sql": outcome.sql,
                "attemptsUsed": outcome.attempts_used,
                "status": "passed",
            },
        )
        return TextToSQLRuntimeResponse.success(outcome.sql)

    @staticmethod
    def _notify_trace_observer(
        trace_observer: Callable[[dict[str, Any]], None] | None,
        event: dict[str, Any],
    ) -> None:
        """Publish optional diagnostics without changing the runtime response."""

        if trace_observer is None:
            return
        try:
            trace_observer(dict(event))
        except Exception:
            logger.warning("Text-to-SQL trace observer failed", exc_info=True)


