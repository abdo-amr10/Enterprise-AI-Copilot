"""Central Latency Audit facade providing fail-open stage spans, prompt profiling, and event logging."""
from __future__ import annotations

import contextlib
import hashlib
import time
from collections.abc import Iterator
from typing import Any

from src.observability.audit_context import (
    RequestAuditContext,
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


@contextlib.contextmanager
def request_lifecycle(
    request_id: str,
    correlation_id: str | None = None,
    traceparent: str | None = None,
) -> Iterator[RequestAuditContext]:
    """Top-level context manager governing an entire AI request lifecycle.

    Initializes the RequestAuditContext, binds it to contextvars, takes system snapshots,
    captures request start and end, and emits the final request summary event.
    """
    ctx = RequestAuditContext(
        request_id=request_id,
        correlation_id=correlation_id,
        traceparent=traceparent,
    )
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
            ctx.end_time = time.perf_counter()
            ctx.total_duration_ms = max(0.0, (ctx.end_time - ctx.start_time) * 1000.0)

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
    is_leaf: bool = True,
    metadata: dict[str, Any] | None = None,
) -> Iterator[None]:
    """Time a pipeline stage or sub-stage.

    If is_leaf=True, the duration is recorded in leaf_stage_durations_ms for
    accurate unaccounted latency calculation without nested double counting.
    """
    ctx = get_current_audit()
    t_start = time.perf_counter()

    if ctx is not None:
        try:
            ctx.final_stage = stage_name
            ctx.span_stack.append((stage_name, t_start, is_leaf))

            write_audit_event({
                "event": "stage_start",
                "request_id": ctx.request_id,
                "stage": stage_name,
                "is_leaf": is_leaf,
                **(metadata or {}),
            })
        except Exception:
            pass

    try:
        yield
    finally:
        dur_ms = max(0.0, (time.perf_counter() - t_start) * 1000.0)
        if ctx is not None:
            try:
                if ctx.span_stack and ctx.span_stack[-1][0] == stage_name:
                    ctx.span_stack.pop()

                if is_leaf:
                    ctx.record_leaf_duration(stage_name, dur_ms)

                write_audit_event({
                    "event": "stage_end",
                    "request_id": ctx.request_id,
                    "stage": stage_name,
                    "is_leaf": is_leaf,
                    "duration_ms": round(dur_ms, 2),
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
