"""Deterministic, storage-free formatting of Backend execution results."""

from __future__ import annotations

import base64
from datetime import datetime, timezone

from src.application.dto.backend.copilot.execution_result import BackendExecutionResult
from src.application.dto.backend.copilot.post_query_response import PostQueryResponse
from src.application.services.post_query_response.excel_result_exporter import ExcelResultExporter
from src.config.post_query_response_settings import PostQueryResponseSettings


class PostQueryResponseFormatter:
    """Classify a result and return inline data or an in-memory Excel file."""

    def __init__(self, settings: PostQueryResponseSettings | None = None,
                 excel_exporter: ExcelResultExporter | None = None) -> None:
        self._settings = settings or PostQueryResponseSettings()
        self._excel_exporter = excel_exporter or ExcelResultExporter()

    def format(self, question: str, result: BackendExecutionResult) -> PostQueryResponse:
        if result.status == "Failed":
            return PostQueryResponse(
                status="Failed", presentation_type="Error",
                text="I’m sorry, but I couldn’t complete that request right now. Please try again.",
                error_code=result.error_code or "BACKEND_EXECUTION_FAILED",
            )
        if result.effective_row_count == 0:
            return PostQueryResponse(status="Success", presentation_type="Empty",
                                     text="I couldn’t find any matching information.", row_count=0)
        if result.effective_row_count > self._settings.max_inline_rows:
            return self._large_table(result)
        if len(result.columns) == 1 and result.effective_row_count == 1:
            return PostQueryResponse(
                status="Success", presentation_type="SingleValue",
                text=(f"Here’s the information you requested: "
                      f"{result.columns[0]} is {result.rows[0][0]}."),
                columns=result.columns, rows=result.rows, row_count=result.effective_row_count,
            )
        return PostQueryResponse(
            status="Success", presentation_type="Table",
            text=("Here’s the information you requested. "
                  f"The result contains {result.effective_row_count} row(s)."),
            columns=result.columns, rows=result.rows, row_count=result.effective_row_count,
        )

    def _large_table(self, result: BackendExecutionResult) -> PostQueryResponse:
        payload = self._excel_exporter.export(result.columns, result.rows)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return PostQueryResponse(
            status="Success", presentation_type="Excel",
            text=(f"Here’s the information you requested. The complete "
                  f"{result.effective_row_count}-row result is available in the attached Excel file."),
            row_count=result.effective_row_count,
            file_name=f"copilot-results-{timestamp}.xlsx",
            content_type=self._excel_exporter.content_type,
            file_content_base64=base64.b64encode(payload).decode("ascii"),
        )
