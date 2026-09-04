"""Central Latency Audit facade providing fail-open stage spans, prompt profiling, and event logging."""
from __future__ import annotations

import contextlib
import hashlib
import time
from collections.abc import Iterator
from typing import Any

from src.observability.audit_context import (
    AuditSpan,
    RequestAuditContext,
    finalize_span,
    get_current_audit,
    reset_current_audit,
    set_current_audit,
)
from src.observability.audit_logger import write_audit_event
from src.observability.audit_summary import build_request_summary
from src.observability.http_audit import build_http_audit_event
from src.observability.ollama_audit import parse_ollama_metrics
from src.observability.system_metrics import capture_system_snapshot


def compute_hash(text: str | None) -> str:
    """Compute SHA-256 hash of a string safely."""
    if not text:
        return ""
    try:
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    except Exception:
        return ""


def format_duration(duration_ms: float) -> str:
    """Format duration with sub-second precision (seconds if >= 1000ms, else ms)."""
    if duration_ms >= 1000.0:
        return f"{duration_ms / 1000.0:.3f} s"
    return f"{duration_ms:.2f} ms"


@contextlib.contextmanager
def request_lifecycle(
    request_id: str,
    correlation_id: str | None = None,
    traceparent: str | None = None,
) -> Iterator[RequestAuditContext]:
    """Top-level context manager governing an entire AI request lifecycle.

    Initializes the RequestAuditContext, binds it to contextvars, takes system snapshots,
    captures request start and end, and emits the final request summary event.
    Re-uses active context if already set (e.g. by ASGI middleware).
    """
    existing_ctx = get_current_audit()
    if existing_ctx is not None:
        yield existing_ctx
        return

    ctx = RequestAuditContext(
        request_id=request_id,
        correlation_id=correlation_id,
        traceparent=traceparent,
    )
    root_span = AuditSpan(
        span_id=f"req_{ctx.start_time_ns}",
        parent_span_id=None,
        name="request",
        stage="request",
        operation="http_request",
        start_time_ns=ctx.start_time_ns,
        is_leaf=False,
    )
    ctx.root_span = root_span
    ctx.active_spans.append(root_span)
    ctx.all_spans.append(root_span)

    token = set_current_audit(ctx)

    try:
        start_sys = capture_system_snapshot()
        ctx.metadata["start_system_snapshot"] = start_sys

        write_audit_event({
            "event": "request_start",
            "request_id": ctx.request_id,
            "correlation_id": ctx.correlation_id,
            "traceparent": ctx.traceparent,
            "system": start_sys,
        })
    except Exception:
        pass

    try:
        yield ctx
        ctx.success = True
    except Exception as exc:
        ctx.success = False
        ctx.error_type = type(exc).__name__
        raise
    finally:
        try:
            end_ns = time.perf_counter_ns()
            ctx.end_time_ns = end_ns
            ctx.end_time = time.perf_counter()
            ctx.total_duration_ms = max(0.0, (end_ns - ctx.start_time_ns) / 1_000_000.0)

            if ctx.root_span:
                finalize_span(ctx.root_span, end_ns, status="ok" if ctx.success else "error")

            end_sys = capture_system_snapshot()
            ctx.metadata["end_system_snapshot"] = end_sys

            summary = build_request_summary(ctx)
            write_audit_event(summary)
        except Exception:
            pass
        finally:
            reset_current_audit(token)


@contextlib.contextmanager
def stage(
    stage_name: str,
    operation: str | None = None,
    is_leaf: bool = True,
    metadata: dict[str, Any] | None = None,
) -> Iterator[AuditSpan | None]:
    """Time a pipeline stage or sub-stage with hierarchical span tracking.

    If is_leaf=True, the duration is recorded in leaf_stage_durations_ms for
    backward-compatible flat accounting without nested double counting.
    """
    ctx = get_current_audit()
    t_start_ns = time.perf_counter_ns()
    t_start = time.perf_counter()
    span: AuditSpan | None = None

    if ctx is not None:
        try:
            parent_span = ctx.active_spans[-1] if ctx.active_spans else None
            parent_span_id = parent_span.span_id if parent_span else None
            op_name = operation or stage_name
            span_id = f"{stage_name}_{t_start_ns}"

            span = AuditSpan(
                span_id=span_id,
                parent_span_id=parent_span_id,
                name=stage_name,
                stage=parent_span.stage if (parent_span and parent_span.stage not in ("request", "pipeline")) else stage_name,
                operation=op_name,
                start_time_ns=t_start_ns,
                is_leaf=is_leaf,
                metadata=dict(metadata or {}),
            )
            if parent_span is not None:
                parent_span.children.append(span)

            ctx.active_spans.append(span)
            ctx.all_spans.append(span)
            ctx.final_stage = stage_name
            ctx.span_stack.append((stage_name, t_start, is_leaf))

            write_audit_event({
                "event": "stage_start",
                "request_id": ctx.request_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "stage": stage_name,
                "operation": op_name,
                "is_leaf": is_leaf,
                **(metadata or {}),
            })
        except Exception:
            pass

    status = "ok"
    try:
        yield span
    except Exception as exc:
        status = "error"
        if span is not None:
            span.status = "error"
            span.metadata["error_type"] = type(exc).__name__
        raise
    finally:
        t_end_ns = time.perf_counter_ns()
        dur_ms = max(0.0, (t_end_ns - t_start_ns) / 1_000_000.0)
        if ctx is not None:
            try:
                if ctx.span_stack and ctx.span_stack[-1][0] == stage_name:
                    ctx.span_stack.pop()

                if span is not None:
                    finalize_span(span, t_end_ns, status=status)
                    if ctx.active_spans and ctx.active_spans[-1].span_id == span.span_id:
                        ctx.active_spans.pop()

                if is_leaf:
                    ctx.record_leaf_duration(stage_name, dur_ms)

                write_audit_event({
                    "event": "stage_end",
                    "request_id": ctx.request_id,
                    "span_id": span.span_id if span else None,
                    "parent_span_id": span.parent_span_id if span else None,
                    "stage": stage_name,
                    "operation": span.operation if span else stage_name,
                    "is_leaf": is_leaf,
                    "duration_ms": round(dur_ms, 2),
                    "inclusive_duration_ms": round(span.inclusive_duration_ms, 2) if span else round(dur_ms, 2),
                    "exclusive_duration_ms": round(span.exclusive_duration_ms, 2) if span else round(dur_ms, 2),
                    "child_covered_duration_ms": round(span.child_covered_duration_ms, 2) if span else 0.0,
                    "orchestration_gaps_ms": round(span.orchestration_gaps_ms, 2) if span else 0.0,
                    "unaccounted_ms": round(span.unaccounted_ms, 2) if span else 0.0,
                    "status": status,
                    **(metadata or {}),
                })
            except Exception:
                pass


def record_prompt(
    stage_name: str,
    model: str,
    config_name: str,
    prompt: str,
    components: dict[str, int] | None = None,
) -> None:
    """Audit prompt assembly metrics, component character counts, and prompt hash."""
    ctx = get_current_audit()
    if ctx is None:
        return

    try:
        prompt_chars = len(prompt)
        prompt_bytes = len(prompt.encode("utf-8", errors="replace"))
        # Lightweight estimation: 1 token ~= 4 characters / 0.75 words
        est_tokens = max(1, len(prompt.split()) * 4 // 3)
        prompt_h = compute_hash(prompt)

        is_dup = ctx.check_and_register_hash("prompt", prompt_h)
        if is_dup:
            ctx.increment_count("duplicate_prompts")

        write_audit_event({
            "event": "prompt_assembly",
            "request_id": ctx.request_id,
            "stage": stage_name,
            "model": model,
            "config_name": config_name,
            "prompt_chars": prompt_chars,
            "prompt_bytes": prompt_bytes,
            "estimated_prompt_tokens": est_tokens,
            "prompt_hash": prompt_h[:16],
            "is_duplicate": is_dup,
            "components": components or {},
        })
    except Exception:
        pass


def record_llm_call(
    stage_name: str,
    model: str,
    config_name: str,
    options_sent: dict[str, Any],
    raw_response: Any,
    client_duration_ms: float,
    estimated_prompt_tokens: int | None = None,
) -> None:
    """Audit an LLM generation call, extracting native Ollama metrics and truncation status."""
    ctx = get_current_audit()
    request_id = ctx.request_id if ctx else None
    if ctx:
        ctx.increment_count("llm_calls")

    try:
        num_ctx = int(options_sent.get("num_ctx", 4096))
        num_predict = int(options_sent.get("num_predict", 2048))

        ollama_data = parse_ollama_metrics(
            raw_response,
            context_length=num_ctx,
            max_output_tokens=num_predict,
            estimated_prompt_tokens=estimated_prompt_tokens,
            client_duration_ms=client_duration_ms,
        )

        if ctx and ollama_data.get("is_cold_load"):
            ctx.increment_count("cold_loads")

        write_audit_event({
            "event": "llm_complete",
            "request_id": request_id,
            "stage": stage_name,
            "model": model,
            "config_name": config_name,
            "runtime": "ollama",
            "options_sent": options_sent,
            **ollama_data,
        })
    except Exception:
        pass


def record_backend_call(
    stage_name: str,
    method: str,
    url: str,
    status_code: int | None,
    duration_ms: float,
    request_bytes: int = 0,
    response_bytes: int = 0,
    timeout: float | None = None,
    retry_count: int = 0,
    exception: Exception | None = None,
    client_preparation_ms: float = 0.0,
    http_request_duration_ms: float = 0.0,
    response_processing_ms: float = 0.0,
    backend_request_id: str | None = None,
    parent_request_id: str | None = None,
) -> None:
    """Audit an HTTP call from AI to Backend."""
    ctx = get_current_audit()
    request_id = ctx.request_id if ctx else None

    is_dup = False
    if ctx:
        ctx.increment_count("backend_calls")
        backend_sig = f"{method.upper()}:{url.split('?')[0]}"
        is_dup = ctx.check_and_register_hash("backend", backend_sig)
        if is_dup:
            ctx.increment_count("duplicate_backend_calls")

    try:
        event = build_http_audit_event(
            request_id=request_id,
            stage=stage_name,
            method=method,
            url=url,
            status_code=status_code,
            duration_ms=duration_ms,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            timeout=timeout,
            retry_count=retry_count,
            exception=exception,
            is_duplicate=is_dup,
            client_preparation_ms=client_preparation_ms,
            http_request_duration_ms=http_request_duration_ms,
            response_processing_ms=response_processing_ms,
            backend_request_id=backend_request_id,
            parent_request_id=parent_request_id,
        )
        write_audit_event(event)
    except Exception:
        pass


def record_validation(
    stage_name: str,
    sql: str,
    is_valid: bool,
    findings: list[str] | list[Any],
    duration_ms: float,
    sub_stages: dict[str, float] | None = None,
) -> None:
    """Audit deterministic SQL validation sub-stages, finding categories, and SQL hashes."""
    ctx = get_current_audit()
    request_id = ctx.request_id if ctx else None
    if ctx:
        ctx.increment_count("validation_calls")

    try:
        sql_h = compute_hash(sql)
        is_dup = False
        if ctx:
            is_dup = ctx.check_and_register_hash("sql", sql_h)
            if is_dup:
                ctx.increment_count("duplicate_sql")

        categories: list[str] = []
        for finding in findings:
            if hasattr(finding, "type"):
                categories.append(str(finding.type))
            else:
                categories.append(str(finding)[:40])

        write_audit_event({
            "event": "validation_complete",
            "request_id": request_id,
            "stage": stage_name,
            "sql_length": len(sql) if sql else 0,
            "sql_hash": sql_h[:16],
            "is_valid": is_valid,
            "findings_count": len(findings),
            "finding_categories": categories,
            "duration_ms": round(duration_ms, 2),
            "is_duplicate_sql": is_dup,
            "sub_stages_ms": sub_stages or {},
        })
    except Exception:
        pass


def record_critic(
    status: str,
    findings_count: int,
    finding_categories: list[str],
    total_duration_ms: float,
    llm_duration_ms: float,
    verifier_duration_ms: float,
    output_chars: int = 0,
) -> None:
    """Audit SQL Critic semantic review duration breakdown and verifier findings."""
    ctx = get_current_audit()
    request_id = ctx.request_id if ctx else None
    if ctx:
        ctx.increment_count("critic_calls")

    try:
        write_audit_event({
            "event": "critic_complete",
            "request_id": request_id,
            "stage": "sql_critic",
            "status": status,
            "findings_count": findings_count,
            "finding_categories": finding_categories,
            "total_duration_ms": round(total_duration_ms, 2),
            "llm_duration_ms": round(llm_duration_ms, 2),
            "verifier_duration_ms": round(verifier_duration_ms, 2),
            "output_chars": output_chars,
        })
    except Exception:
        pass


def record_correction_attempt(
    attempt: int,
    trigger_reason: str,
    duration_ms: float,
    previous_sql: str | None = None,
    new_sql: str | None = None,
    issues_count: int = 0,
) -> None:
    """Audit an individual self-correction attempt iteration."""
    ctx = get_current_audit()
    request_id = ctx.request_id if ctx else None
    if ctx:
        ctx.increment_count("correction_attempts")

    try:
        prev_h = compute_hash(previous_sql)
        new_h = compute_hash(new_sql)
        write_audit_event({
            "event": "correction_attempt",
            "request_id": request_id,
            "stage": "self_correction",
            "attempt": attempt,
            "trigger_reason": trigger_reason,
            "duration_ms": round(duration_ms, 2),
            "previous_sql_hash": prev_h[:16],
            "new_sql_hash": new_h[:16],
            "issues_count": issues_count,
        })
    except Exception:
        pass
