"""HTTP entry point for the AI-owned portion of `POST /api/v1/copilot/ask`.

This router is intentionally thin: receive, build the existing DTO,
delegate to CopilotRuntimePipeline (which now also runs Self-
Correction internally), return its response. No business logic lives
here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from src.api.internal_auth import require_internal_service

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
from src.api.contracts import CopilotRequest, CopilotResponse, PostQueryFormatRequest

router = APIRouter(prefix="/internal/copilot", tags=["copilot"], dependencies=[Depends(require_internal_service)])


@router.post("/text-to-sql")
def text_to_sql(
    request: CopilotRequest,
    pipeline: CopilotRuntimePipeline = Depends(get_copilot_pipeline),
)-> CopilotResponse:
    if request.conversation:
        raise HTTPException(status_code=422, detail="conversation is not supported by the current Text-to-SQL runtime.")
    try:
        ask_request = CopilotAskRequest(question=request.question, conversation=())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    result = pipeline.run(ask_request)

    return CopilotResponse(
        status=result.status,
        sql=result.sql,
        errorCode=result.error_code,
        message=result.message,
        failureReason=result.failure_reason,
        rewrittenQuestion=result.rewritten_question,
        suggestions=list(result.suggestions),
    )


@router.post("/format-execution-result")
def format_execution_result(
    request: PostQueryFormatRequest,
    formatter: PostQueryResponseFormatter = Depends(get_post_query_response_formatter),
) -> dict:
    """Format a Backend-owned execution result without executing SQL or persisting files."""

    try:
        payload = request.executionResult
        result = BackendExecutionResult(
            status=payload.status,
            columns=tuple(payload.columns),
            rows=tuple(tuple(row) for row in payload.rows),
            row_count=payload.rowCount,
            error_code=payload.errorCode,
            error_message=payload.errorMessage,
            metadata=payload.metadata,
        )
        return formatter.format(request.question, result).to_dict()
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
