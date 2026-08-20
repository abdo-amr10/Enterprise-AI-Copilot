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
from src.application.services.text_to_sql.reference_data_preflight import ReferenceDataPreflight

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
        reference_data_preflight: ReferenceDataPreflight | None = None,
    ) -> None:
        self._text_to_sql_pipeline = text_to_sql_pipeline
        # Optional so existing callers/tests that build this pipeline with
        # only a TextToSQLPipeline keep working unchanged (see
        # tests/unit/application/pipelines/text_to_sql/test_copilot_runtime_pipeline.py).
        # Real runtime wiring (src/api/dependencies.py) always supplies a
        # real instance, so Self-Correction always runs after generate.
        self._self_correction_service = self_correction_service
        self._reference_data_preflight = reference_data_preflight

    def run(self, request: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        missing_manager = self._missing_manager_response(request.question)
        if missing_manager is not None:
            return missing_manager

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
            logger.info("Generated model output (invalid structured response): %s", generated.text)
            return TextToSQLRuntimeResponse.failure(
                "SQL_VALIDATION_FAILED",
                "The model response was not a valid structured SQL result.",
                failure_reason="The generation model did not return the required JSON SQL contract.",
            )

        if payload.get("status") != "success":
            warnings = payload.get("warnings")
            reason = "; ".join(str(item) for item in warnings) if isinstance(warnings, list) else None
            logger.info("Generated model output (status is not success): %s", generated.text)
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
            logger.info("Generated model output (unsafe or incomplete SQL payload): %s", generated.text)
            return TextToSQLRuntimeResponse.failure(
                "SQL_VALIDATION_FAILED",
                "The system could not generate a safe read-only query for this request.",
                failure_reason=(
                    "The generated payload was missing SQL, was not marked read-only, "
                    "or contained a forbidden write/administrative operation."
                ),
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
                failure_reason="; ".join(outcome.issues) or "The query remained invalid after correction attempts.",
            )

        return TextToSQLRuntimeResponse.success(outcome.sql)

    def _missing_manager_response(self, question: str) -> TextToSQLRuntimeResponse | None:
        if self._reference_data_preflight is None:
            return None

        result = self._reference_data_preflight.check_branch_manager(question)
        if result is None:
            return None

        requested, managers = result
        suggestions = tuple(
            f"Show all accounts in branches managed by {manager}." for manager in managers
        )
        return TextToSQLRuntimeResponse.failure(
            "REFERENCE_VALUE_NOT_FOUND",
            "No branch manager matching the requested name was found in the available reference data.",
            failure_reason=(
                f"'{requested}' does not exist in branches.manager_name in the local reference dataset."
            ),
            rewritten_question=(
                "Show all accounts in branches managed by <manager name>."
            ),
            suggestions=suggestions,
        )

    

