"""Translate a Copilot question into safe, backend-executable read-only SQL."""

from __future__ import annotations

import json
import re

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.backend.copilot.text_to_sql_runtime_response import (
    TextToSQLRuntimeResponse,
)
from src.application.services.text_to_sql.text_to_sql_pipeline import TextToSQLPipeline


class CopilotRuntimePipeline:
    """AI-owned portion of `POST /api/v1/copilot/ask`.

    This pipeline never executes SQL. The Backend remains responsible for
    authorization, RLS, SQL Server execution, report formatting, and history.
    """

    _FORBIDDEN_SQL = re.compile(
        r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC(?:UTE)?)\b",
        re.IGNORECASE,
    )

    def __init__(self, text_to_sql_pipeline: TextToSQLPipeline) -> None:
        self._text_to_sql_pipeline = text_to_sql_pipeline

    def run(self, request: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        try:
            generated = self._text_to_sql_pipeline.run(question=request.question)
        except Exception:
            return TextToSQLRuntimeResponse.failure(
                "SQL_GENERATION_FAILED",
                "The system could not generate SQL for this request.",
            )

        try:
            payload = json.loads(generated.text)
        except json.JSONDecodeError:
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

        return TextToSQLRuntimeResponse.success(sql.strip())
