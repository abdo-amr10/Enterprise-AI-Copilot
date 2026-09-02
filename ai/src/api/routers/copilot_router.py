"""HTTP entry point for the AI-owned portion of `POST /api/v1/copilot/ask`.

This router is intentionally thin: receive, build the existing DTO,
delegate to CopilotRuntimePipeline (which now also runs Self-
Correction internally), return its response. No business logic lives
here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_copilot_pipeline
from src.api.post_query_dependencies import get_post_query_response_formatter
from src.application.dto.backend.copilot.execution_result import BackendExecutionResult
from src.application.services.post_query_response.post_query_response_formatter import (
    PostQueryResponseFormatter,
)
from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import (
    CopilotRuntimePipeline,
)
from typing import Any

from src.api.contracts import (
    CopilotRequest,
    CopilotResponse,
    ExecutionResultRequest,
    PostQueryFormatRequest,
    PostQueryResponse,
)

router = APIRouter(prefix="/internal/copilot", tags=["copilot"])


def _normalize_execution_result(
    payload: ExecutionResultRequest | list[dict[str, Any]],
) -> BackendExecutionResult:
    if isinstance(payload, list):
        if not payload:
            return BackendExecutionResult(
                status="Success",
                columns=(),
                rows=(),
                row_count=0,
            )
        seen_columns: dict[str, None] = {}
        for row in payload:
            if isinstance(row, dict):
                for key in row.keys():
                    seen_columns[str(key)] = None
        columns = tuple(seen_columns.keys())
        rows = tuple(
            tuple(row.get(col) if isinstance(row, dict) else None for col in columns)
            for row in payload
        )
        return BackendExecutionResult(
            status="Success",
            columns=columns,
            rows=rows,
            row_count=len(rows),
        )

    return BackendExecutionResult(
        status=payload.status,
        columns=tuple(payload.columns),
        rows=tuple(tuple(row) for row in payload.rows),
        row_count=payload.rowCount,
        error_code=payload.errorCode,
        error_message=payload.errorMessage,
        metadata=payload.metadata,
    )


@router.post("/text-to-sql")
def text_to_sql(
    request: CopilotRequest,
    pipeline: CopilotRuntimePipeline = Depends(get_copilot_pipeline),
)-> CopilotResponse:
    try:
        ask_request = CopilotAskRequest(
            question=request.question,
            conversation=tuple(request.conversation or ()),
            correlation_id=request.correlation_id,
            traceparent=request.traceparent,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    result = pipeline.run(ask_request)

    return CopilotResponse(
        isSuccess=result.status == "Success",
        generatedSql=result.sql,
        errorMessage=(
            None
            if result.status == "Success"
            else result.failure_reason or result.message or result.error_code
        ),
    )


@router.post(
    "/format-execution-result",
    response_model=PostQueryResponse,
    response_model_by_alias=True,
)
def format_execution_result(
    request: PostQueryFormatRequest,
    formatter: PostQueryResponseFormatter = Depends(get_post_query_response_formatter),
) -> PostQueryResponse:
    """Format a Backend-owned execution result without executing SQL or persisting files."""

    try:
        result = _normalize_execution_result(request.executionResult)
        return formatter.format(request.question, result)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
