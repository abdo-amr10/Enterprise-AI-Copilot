"""Pure ASGI middleware for end-to-end HTTP request latency auditing and context propagation."""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from src.observability.audit_context import (
    create_audit_context,
    set_current_audit,
    get_current_audit,
    AuditSpan,
    finalize_span,
)
from src.observability.audit_summary import build_request_summary
from src.observability.audit_logger import write_audit_event

logger = logging.getLogger(__name__)


class LatencyAuditASGIMiddleware:
    """Pure ASGI middleware capturing exact end-to-end request latency.

    Times from initial byte/scope receipt until the final http.response.body chunk
    with more_body=False has been sent, capturing FastAPI routing, dependency injection,
    Pydantic validation, serialization, and network send buffer completion.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        t_start_ns = time.perf_counter_ns()
        headers = dict(scope.get("headers", []))

        def _header_val(name: str) -> str | None:
            raw = headers.get(name.lower().encode("latin1"))
            return raw.decode("latin1") if raw else None

        correlation_id = _header_val("x-correlation-id") or _header_val("x-request-id")
        traceparent = _header_val("traceparent")
        request_id = correlation_id or str(uuid.uuid4())

        ctx = create_audit_context(
            request_id=request_id,
            correlation_id=correlation_id,
            traceparent=traceparent,
        )

        path = scope.get("path", "")
        method = scope.get("method", "HTTP")

        root_span = AuditSpan(
            span_id=request_id,
            parent_span_id=None,
            name="request_lifecycle",
            stage="request_lifecycle",
            operation=f"{method} {path}",
            start_time_ns=t_start_ns,
            is_leaf=False,
            metadata={
                "method": method,
                "path": path,
            },
        )
        ctx.root_span = root_span
        ctx.active_spans.append(root_span)
        ctx.all_spans.append(root_span)
        token = set_current_audit(ctx)

        status_code = 200
        response_finalized = False

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code, response_finalized
            msg_type = message.get("type")

            if msg_type == "http.response.start":
                status_code = int(message.get("status", 200))
                # Inject tracing / correlation response headers
                raw_headers = list(message.get("headers", []))
                raw_headers.append((b"x-ai-request-id", request_id.encode("latin1")))
                if correlation_id:
                    raw_headers.append((b"x-correlation-id", correlation_id.encode("latin1")))
                message = {**message, "headers": raw_headers}
                await send(message)
                return

            if msg_type == "http.response.body":
                more_body = message.get("more_body", False)
                await send(message)
                if not more_body and not response_finalized:
                    response_finalized = True
                    t_end_ns = time.perf_counter_ns()
                    total_dur_ms = (t_end_ns - t_start_ns) / 1_000_000.0
                    ctx.total_duration_ms = total_dur_ms
                    pipeline_dur = ctx.pipeline_duration_ms or 0.0
                    ctx.api_framework_overhead_ms = max(0.0, total_dur_ms - pipeline_dur)
                    root_span.metadata["status_code"] = status_code
                    finalize_span(root_span, t_end_ns, status="SUCCESS" if status_code < 400 else "FAILURE")

                    try:
                        summary = build_request_summary(ctx)
                        write_audit_event({
                            "event": "request_end",
                            "request_id": request_id,
                            "correlation_id": correlation_id,
                            "traceparent": traceparent,
                            "method": method,
                            "path": path,
                            "status_code": status_code,
                            "duration_ms": round(total_dur_ms, 2),
                            "pipeline_duration_ms": round(pipeline_dur, 2),
                            "api_framework_overhead_ms": round(ctx.api_framework_overhead_ms, 2),
                            "summary": summary,
                        })
                    except Exception:
                        pass
                return

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            set_current_audit(None)
