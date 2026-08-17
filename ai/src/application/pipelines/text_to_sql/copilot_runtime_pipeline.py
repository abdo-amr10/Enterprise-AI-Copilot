"""Translate a Copilot question into safe, backend-executable read-only SQL."""

from __future__ import annotations

import json
import re
import logging

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
    authorization, RLS, SQL Server execution, report formatting, and history.
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
        r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC(?:UTE)?)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        text_to_sql_pipeline: TextToSQLPipeline,
        self_correction_service: SelfCorrectionService | None = None,
    ) -> None:
        self._text_to_sql_pipeline = text_to_sql_pipeline
        # Optional so existing callers/tests that build this pipeline with
        # only a TextToSQLPipeline keep working unchanged (see
        # tests/unit/application/pipelines/text_to_sql/test_copilot_runtime_pipeline.py).
        # Real runtime wiring (src/api/dependencies.py) always supplies a
        # real instance, so Self-Correction always runs after generate.
        self._self_correction_service = self_correction_service

    def run(self, request: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        try:
            if self._self_correction_service is None:
                generated = self._text_to_sql_pipeline.run(question=request.question)
                semantic_context = None
            else:
                semantic_context = self._text_to_sql_pipeline.build_context(request.question)
                generated = self._text_to_sql_pipeline.run(
                    question=request.question,
                    semantic_context=semantic_context,
                )
        except Exception:
                logger.exception("Text-to-SQL generation failed")
                return TextToSQLRuntimeResponse.failure(
                    "SQL_GENERATION_FAILED",
                    "The system could not generate SQL for this request.",  )
        try:
            payload = self._parse_generation_response(generated.text)
        except (json.JSONDecodeError, ValueError):
            return TextToSQLRuntimeResponse.failure(
                "SQL_VALIDATION_FAILED",
                "The model response was not a valid structured SQL result.",
            )

        if payload.get("status") != "success":
            return TextToSQLRuntimeResponse.failure(
                "SQL_VALIDATION_FAILED",
                "The system could not generate a safe read-only query for this request.",
            )

        sql = payload.get("sql")
        if (
            not isinstance(sql, str)
            or not sql.strip()
            or payload.get("is_read_only") is not True
            or self._FORBIDDEN_SQL.search(sql)
        ):
            return TextToSQLRuntimeResponse.failure(
                "SQL_VALIDATION_FAILED",
                "The system could not generate a safe read-only query for this request.",
            )

        sql = sql.strip()

        if self._self_correction_service is None:
            return TextToSQLRuntimeResponse.success(sql)

        outcome = self._self_correction_service.run(
            question=request.question,
            sql=sql,
            semantic_context=semantic_context,
        )

        if not outcome.is_valid:
            return TextToSQLRuntimeResponse.failure(
                "MAX_RETRIES_EXCEEDED",
                "The system could not generate a valid read-only SQL query.",
            )

        return TextToSQLRuntimeResponse.success(outcome.sql)

    

