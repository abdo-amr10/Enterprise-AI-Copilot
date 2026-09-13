"""HTTP entry point for the AI-owned portion of `POST /api/v1/copilot/ask`.

This router is intentionally thin: receive, build the existing DTO,
delegate to CopilotRuntimePipeline (which now also runs Self-
Correction internally), return its response. No business logic lives
here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_conversation_router, get_copilot_pipeline
from src.api.post_query_dependencies import get_post_query_response_formatter
from src.application.dto.backend.copilot.execution_result import BackendExecutionResult
from src.application.services.conversation.router.conversation_router import (
    ConversationRouter,
)
from src.application.services.conversation.router.routing_decision import (
    ConversationRoute,
)
from src.application.services.post_query_response.post_query_response_formatter import (
    PostQueryResponseFormatter,
)
from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import (
    CopilotRuntimePipeline,
)
from typing import Any
from src.observability.conversation_trace_logger import log_trace

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
    conversation_router: ConversationRouter = Depends(get_conversation_router),
) -> CopilotResponse:
    try:
        ask_request = CopilotAskRequest(
            question=request.question,
            conversation=tuple(request.conversation or ()),
            correlation_id=request.correlation_id,
            traceparent=request.traceparent,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    _trace_id = request.correlation_id or "no-trace-id"
    log_trace(
        "ai_runtime.request.received",
        _trace_id,
        question=ask_request.question,
        conversation_count=len(ask_request.conversation),
        conversation_id=request.conversation_id,
        tenant_id=request.tenant_id,
    )
    _conv_roles = [
        (m.get("role", "?") if isinstance(m, dict) else getattr(m, "role", "?"))
        for m in (request.conversation or [])
    ]
    log_trace(
        "ai_runtime.conversation.payload",
        _trace_id,
        roles=_conv_roles,
        message_count=len(request.conversation or []),
        last_result_metadata_present=request.last_result_metadata is not None,
    )

    decision = conversation_router.route(
        question=ask_request.question,
        raw_conversation=ask_request.conversation,
        correlation_id=ask_request.correlation_id,
        conversation_id=request.conversation_id,
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        branch_id=request.branch_id,
        semantic_revision_id=request.semantic_revision_id,
        schema_version=request.schema_version,
        last_result_metadata=request.last_result_metadata,
        executor=pipeline.run,
    )

    log_trace(
        "conversation_router.output",
        _trace_id,
        route=decision.route.value if hasattr(decision.route, "value") else str(decision.route),
        is_success=decision.is_success,
        generated_sql_present=bool(decision.generated_sql),
        generated_sql_preview=(decision.generated_sql[:200] if decision.generated_sql else None),
        direct_answer_present=bool(decision.direct_answer),
        direct_answer_preview=(decision.direct_answer[:200] if decision.direct_answer else None),
        resolved_question=decision.resolved_question,
        error_message=decision.error_message,
    )

    effective_is_success = decision.is_success
    effective_route = decision.route.value if hasattr(decision.route, "value") else str(decision.route)
    effective_direct_answer = decision.direct_answer
    effective_presentation_type = decision.presentation_type
    effective_text_summary = decision.text_summary

    # Adaptations for .NET Backend CopilotService expectations:
    # 1. Out-of-scope safe rejections:
    if decision.route == ConversationRoute.UNSUPPORTED and (decision.error_message or decision.direct_answer):
        effective_route = "SafeRejection"
        effective_is_success = True
        effective_presentation_type = "SafeRejection"
        effective_direct_answer = decision.direct_answer or decision.error_message
        effective_text_summary = effective_direct_answer

    # 2. Clarification needed (UNRESOLVED_CONTEXT):
    elif decision.route == ConversationRoute.UNRESOLVED_CONTEXT and (
        decision.direct_answer or decision.text_summary or decision.error_message
    ):
        effective_route = "UNRESOLVED_CONTEXT"
        effective_is_success = True
        effective_direct_answer = decision.direct_answer or decision.text_summary or decision.error_message
        effective_text_summary = effective_direct_answer

    # 3. Context reset or conversational direct answers without SQL:
    elif not decision.generated_sql and (decision.direct_answer or decision.presentation_type == "DirectAnswer"):
        effective_is_success = True
        effective_direct_answer = decision.direct_answer or decision.text_summary
        effective_text_summary = effective_direct_answer
        if effective_route == ConversationRoute.NEW_DATABASE_QUERY.value:
            effective_route = "DirectAnswer"

    # 4. Negative replay with direct answer:
    elif decision.route == ConversationRoute.EXACT_REPLAY and not decision.generated_sql and decision.direct_answer:
        effective_is_success = True
        effective_direct_answer = decision.direct_answer
        effective_text_summary = decision.text_summary or decision.direct_answer

    fallback_summary = (
        effective_text_summary
        or effective_direct_answer
        or ("Query generated successfully." if decision.generated_sql else "The request was processed successfully.")
    )

    return CopilotResponse(
        isSuccess=effective_is_success,
        generatedSql=decision.generated_sql,
        textSummary=fallback_summary if effective_is_success else effective_text_summary,
        presentationType=effective_presentation_type,
        errorMessage=decision.error_message if not effective_is_success else None,
        route=effective_route,
        directAnswer=effective_direct_answer,
        resolvedQuestion=decision.resolved_question,
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
