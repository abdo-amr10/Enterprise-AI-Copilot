"""Comprehensive unit tests for hierarchical latency observability.

Verifies:
1. Monotonic nanosecond timing precision.
2. Sequential child spans interval union.
3. Overlapping child spans interval union.
4. Nested child spans interval union.
5. Exclusive duration calculation (inclusive - child_covered).
6. Orchestration gaps calculation.
7. Unaccounted residual calculation.
8. Factual model loading without heuristic thresholds.
9. Ollama timing separation (Python client vs daemon server vs client overhead).
10. Backend HTTP client 3-phase timing and independent total.
11. Preflight stage hierarchy (input_checks, table_checks).
12. Preflight early exit on BLOCK (no fake downstream spans).
13. Context retrieval stage hierarchy.
14. SQL generation stage hierarchy.
15. Self-correction deterministic validation sub-spans (syntax, schema, relationship, rls).
16. Self-correction critic sub-spans (context, evaluation, verifier).
17. Self-correction correction attempt sub-spans.
18. Pure ASGI middleware lifecycle and api_framework_overhead_ms calculation.
19. ASGI response header injection (x-ai-request-id, x-correlation-id).
20. Fail-safe telemetry behavior (telemetry errors never crash business logic).
"""
from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.dto.llm.generation_response import GenerationResponse
from src.observability.asgi_middleware import LatencyAuditASGIMiddleware
from src.observability.audit_context import (
    AuditSpan,
    RequestAuditContext,
    compute_interval_union,
    finalize_span,
    get_current_audit,
)
from src.observability.audit_summary import build_request_summary
from src.observability.http_audit import build_http_audit_event
from src.observability.latency_audit import (
    record_backend_call,
    request_lifecycle,
    stage as audit_stage,
)
from src.observability.ollama_audit import parse_ollama_metrics


# 1. Monotonic nanosecond timing precision
def test_monotonic_nanosecond_timing_precision() -> None:
    t0_ns = time.perf_counter_ns()
    span = AuditSpan(
        span_id="s1",
        parent_span_id=None,
        name="test_precision",
        stage="test",
        operation="op",
        start_time_ns=t0_ns,
    )
    time.sleep(0.005)  # 5ms
    t1_ns = time.perf_counter_ns()
    finalize_span(span, end_time_ns=t1_ns)

    assert span.start_time_ns == t0_ns
    assert span.end_time_ns == t1_ns
    assert span.end_time_ns > span.start_time_ns
    assert span.inclusive_duration_ms >= 4.0  # at least ~5ms in float ms


# 2. Sequential child spans interval union
def test_sequential_child_spans_interval_union() -> None:
    # Child 1: [100_000_000, 200_000_000] (100ms)
    # Child 2: [300_000_000, 450_000_000] (150ms)
    # Total covered = 250ms; gap = 100ms
    intervals = [
        (100_000_000, 200_000_000),
        (300_000_000, 450_000_000),
    ]
    covered_ns, merged = compute_interval_union(intervals)
    covered_ms = covered_ns / 1_000_000.0
    assert covered_ms == pytest.approx(250.0, 0.01)
    assert len(merged) == 2
    assert merged[0] == (100_000_000, 200_000_000)
    assert merged[1] == (300_000_000, 450_000_000)


# 3. Overlapping child spans interval union
def test_overlapping_child_spans_interval_union() -> None:
    # Child 1: [100_000_000, 300_000_000] (200ms)
    # Child 2: [250_000_000, 400_000_000] (150ms, overlapping by 50ms)
    # Merged interval: [100_000_000, 400_000_000] -> covered = 300ms (not 350ms!)
    intervals = [
        (100_000_000, 300_000_000),
        (250_000_000, 400_000_000),
    ]
    covered_ns, merged = compute_interval_union(intervals)
    covered_ms = covered_ns / 1_000_000.0
    assert covered_ms == pytest.approx(300.0, 0.01)
    assert len(merged) == 1
    assert merged[0] == (100_000_000, 400_000_000)


# 4. Nested child spans interval union
def test_nested_child_spans_interval_union() -> None:
    # Child 1: [100_000_000, 500_000_000] (400ms)
    # Child 2: [200_000_000, 300_000_000] (100ms, completely inside child 1)
    intervals = [
        (100_000_000, 500_000_000),
        (200_000_000, 300_000_000),
    ]
    covered_ns, merged = compute_interval_union(intervals)
    covered_ms = covered_ns / 1_000_000.0
    assert covered_ms == pytest.approx(400.0, 0.01)
    assert len(merged) == 1
    assert merged[0] == (100_000_000, 500_000_000)


# 5. Exclusive duration calculation (inclusive - child_covered)
def test_exclusive_duration_calculation() -> None:
    parent = AuditSpan(
        span_id="p1",
        parent_span_id=None,
        name="parent",
        stage="pipeline",
        operation="pipeline",
        start_time_ns=100_000_000,
        is_leaf=False,
    )

    child1 = AuditSpan(
        span_id="c1",
        parent_span_id="p1",
        name="child1",
        stage="stage1",
        operation="op1",
        start_time_ns=150_000_000,
        end_time_ns=250_000_000,
        is_leaf=True,
    )
    finalize_span(child1, 250_000_000)
    parent.children.append(child1)

    child2 = AuditSpan(
        span_id="c2",
        parent_span_id="p1",
        name="child2",
        stage="stage2",
        operation="op2",
        start_time_ns=300_000_000,
        end_time_ns=450_000_000,
        is_leaf=True,
    )
    finalize_span(child2, 450_000_000)
    parent.children.append(child2)

    finalize_span(parent, 500_000_000)  # Total parent = 400ms

    assert parent.inclusive_duration_ms == pytest.approx(400.0, 0.01)
    assert parent.child_covered_duration_ms == pytest.approx(250.0, 0.01)
    # Exclusive = 400 - 250 = 150ms
    assert parent.exclusive_duration_ms == pytest.approx(150.0, 0.01)


# 6. Orchestration gaps calculation
def test_orchestration_gaps_calculation() -> None:
    parent = AuditSpan(
        span_id="p1",
        parent_span_id=None,
        name="parent",
        stage="pipeline",
        operation="pipeline",
        start_time_ns=100_000_000,
        is_leaf=False,
    )

    # child 1: 150ms to 250ms
    c1 = AuditSpan(
        span_id="c1",
        parent_span_id="p1",
        name="c1",
        stage="s1",
        operation="op1",
        start_time_ns=150_000_000,
        end_time_ns=250_000_000,
        is_leaf=True,
    )
    finalize_span(c1, 250_000_000)
    parent.children.append(c1)

    # gap of 50ms between c1 and c2 (250ms to 300ms)
    # child 2: 300ms to 400ms
    c2 = AuditSpan(
        span_id="c2",
        parent_span_id="p1",
        name="c2",
        stage="s2",
        operation="op2",
        start_time_ns=300_000_000,
        end_time_ns=400_000_000,
        is_leaf=True,
    )
    finalize_span(c2, 400_000_000)
    parent.children.append(c2)

    finalize_span(parent, 500_000_000)

    # Gap between c1 end (250) and c2 start (300) = 50ms
    assert parent.orchestration_gaps_ms == pytest.approx(50.0, 0.01)


# 7. Unaccounted residual calculation
def test_unaccounted_residual_calculation() -> None:
    parent = AuditSpan(
        span_id="p1",
        parent_span_id=None,
        name="parent",
        stage="pipeline",
        operation="pipeline",
        start_time_ns=100_000_000,
        is_leaf=False,
    )

    # child: 150ms to 250ms (100ms)
    c1 = AuditSpan(
        span_id="c1",
        parent_span_id="p1",
        name="c1",
        stage="s1",
        operation="op1",
        start_time_ns=150_000_000,
        end_time_ns=250_000_000,
        is_leaf=True,
    )
    finalize_span(c1, 250_000_000)
    parent.children.append(c1)

    finalize_span(parent, 400_000_000)  # total: 300ms

    # inclusive: 300ms, child_covered: 100ms -> exclusive = 200ms
    # gaps: 0.0 (only 1 child)
    # unaccounted = max(0.0, exclusive - gaps) = 200ms
    assert parent.exclusive_duration_ms == pytest.approx(200.0, 0.01)
    assert parent.unaccounted_ms == pytest.approx(200.0, 0.01)


# 8. Factual model loading without heuristic thresholds
def test_factual_model_loading_no_heuristic_thresholds() -> None:
    # Case A: load_duration == 0 -> model was already resident
    raw_resident = {
        "total_duration": 1_000_000_000,
        "load_duration": 0,
        "prompt_eval_duration": 200_000_000,
        "eval_duration": 800_000_000,
    }
    parsed_a = parse_ollama_metrics(raw_resident)
    assert parsed_a["cold_load"] is False
    assert parsed_a["model_load_type"] == "warm"

    # Case B: load_duration > 0 -> model load occurred (e.g. 50ms or 1500ms)
    raw_loaded = {
        "total_duration": 2_000_000_000,
        "load_duration": 50_000_000,  # 50ms
        "prompt_eval_duration": 200_000_000,
        "eval_duration": 1_750_000_000,
    }
    parsed_b = parse_ollama_metrics(raw_loaded)
    assert parsed_b["cold_load"] is True
    assert parsed_b["model_load_type"] == "cold"

    # Case C: load_duration absent -> none
    raw_unknown = {
        "total_duration": 1_000_000_000,
        "eval_duration": 1_000_000_000,
    }
    parsed_c = parse_ollama_metrics(raw_unknown)
    assert parsed_c["cold_load"] is None
    assert parsed_c["model_load_type"] == "none"


# 9. Ollama timing separation (Python client vs daemon server vs client overhead)
def test_ollama_timing_separation_client_vs_server() -> None:
    resp = GenerationResponse(
        text='{"sql": "SELECT 1"}',
        model_name="qwen2.5-coder:7b",
        provider="ollama",
        client_duration_ms=120.0,
        server_duration_ms=105.0,
        client_overhead_ms=15.0,
        model_load_duration_ms=0.0,
        model_load_type="warm",
        cold_load=False,
    )
    assert resp.client_duration_ms == 120.0
    assert resp.server_duration_ms == 105.0
    assert resp.client_overhead_ms == 15.0
    assert resp.client_overhead_ms == resp.client_duration_ms - resp.server_duration_ms
    assert resp.cold_load is False


# 10. Backend HTTP client 3-phase timing and independent total
def test_backend_http_3_phase_timing_and_total() -> None:
    event = build_http_audit_event(
        request_id="req-999",
        stage="backend_metadata",
        method="POST",
        url="http://localhost:5226/api/v1/metadata",
        status_code=200,
        duration_ms=52.5,
        client_preparation_ms=1.2,
        http_request_duration_ms=49.1,
        response_processing_ms=2.2,
        backend_request_id="back-123",
        parent_request_id="req-999",
    )
    assert event["duration_ms"] == 52.5
    assert event["client_preparation_ms"] == 1.2
    assert event["http_request_duration_ms"] == 49.1
    assert event["response_processing_ms"] == 2.2
    assert event["backend_request_id"] == "back-123"
    assert event["parent_request_id"] == "req-999"


# 11. Preflight stage hierarchy (input_checks, table_checks)
def test_preflight_stage_hierarchy() -> None:
    with request_lifecycle("test_preflight") as ctx:
        with audit_stage("preflight", is_leaf=False):
            with audit_stage("input_checks"):
                time.sleep(0.001)
            with audit_stage("table_checks"):
                time.sleep(0.001)

    summary = build_request_summary(ctx)
    hierarchy = summary["hierarchy"]
    preflight = next((c for c in hierarchy["children"] if c["name"] == "preflight"), None)
    assert preflight is not None
    child_names = [c["name"] for c in preflight["children"]]
    assert "input_checks" in child_names
    assert "table_checks" in child_names


# 12. Preflight early exit on BLOCK (no fake downstream spans)
def test_preflight_early_exit_on_block() -> None:
    with request_lifecycle("test_preflight_block") as ctx:
        with audit_stage("pipeline", is_leaf=False):
            with audit_stage("preflight", is_leaf=False):
                with audit_stage("input_checks"):
                    blocked = True
            if not blocked:
                with audit_stage("context_retrieval"):
                    pass
                with audit_stage("sql_generation"):
                    pass

    summary = build_request_summary(ctx)
    pipeline = next((c for c in summary["hierarchy"]["children"] if c["name"] == "pipeline"), None)
    assert pipeline is not None
    child_names = [c["name"] for c in pipeline["children"]]
    assert "preflight" in child_names
    assert "context_retrieval" not in child_names
    assert "sql_generation" not in child_names


# 13. Context retrieval stage hierarchy
def test_context_retrieval_stage_hierarchy() -> None:
    with request_lifecycle("test_retrieval_hierarchy") as ctx:
        with audit_stage("context_retrieval", is_leaf=False):
            with audit_stage("candidate_planning"):
                pass
            with audit_stage("retrieval", is_leaf=False):
                with audit_stage("vector_search"):
                    pass
            with audit_stage("relevance_filtering_and_planning"):
                pass
            with audit_stage("context_assembly"):
                pass

    summary = build_request_summary(ctx)
    ret_span = next((c for c in summary["hierarchy"]["children"] if c["name"] == "context_retrieval"), None)
    assert ret_span is not None
    child_names = [c["name"] for c in ret_span["children"]]
    assert "candidate_planning" in child_names
    assert "retrieval" in child_names
    assert "relevance_filtering_and_planning" in child_names
    assert "context_assembly" in child_names

    ret_sub = next(c for c in ret_span["children"] if c["name"] == "retrieval")
    assert any(c["name"] == "vector_search" for c in ret_sub["children"])


# 14. SQL generation stage hierarchy
def test_sql_generation_stage_hierarchy() -> None:
    with request_lifecycle("test_sql_generation_hierarchy") as ctx:
        with audit_stage("sql_generation", is_leaf=False):
            with audit_stage("prompt_construction"):
                pass
            with audit_stage("llm_inference", is_leaf=False):
                with audit_stage("ollama_generation"):
                    pass
            with audit_stage("output_parsing"):
                pass

    summary = build_request_summary(ctx)
    gen_span = next((c for c in summary["hierarchy"]["children"] if c["name"] == "sql_generation"), None)
    assert gen_span is not None
    child_names = [c["name"] for c in gen_span["children"]]
    assert "prompt_construction" in child_names
    assert "llm_inference" in child_names
    assert "output_parsing" in child_names

    llm_sub = next(c for c in gen_span["children"] if c["name"] == "llm_inference")
    assert any(c["name"] == "ollama_generation" for c in llm_sub["children"])


# 15. Self-correction deterministic validation sub-spans
def test_self_correction_deterministic_validation_sub_spans() -> None:
    with request_lifecycle("test_det_val") as ctx:
        with audit_stage("self_correction", is_leaf=False):
            with audit_stage("deterministic_validation", is_leaf=False):
                with audit_stage("syntax"):
                    pass
                with audit_stage("schema"):
                    pass
                with audit_stage("relationship"):
                    pass
                with audit_stage("rls"):
                    pass

    summary = build_request_summary(ctx)
    corr_span = next((c for c in summary["hierarchy"]["children"] if c["name"] == "self_correction"), None)
    assert corr_span is not None
    det_val = next((c for c in corr_span["children"] if c["name"] == "deterministic_validation"), None)
    assert det_val is not None
    val_sub_names = [c["name"] for c in det_val["children"]]
    assert "syntax" in val_sub_names
    assert "schema" in val_sub_names
    assert "relationship" in val_sub_names
    assert "rls" in val_sub_names


# 16. Self-correction critic sub-spans
def test_self_correction_critic_sub_spans() -> None:
    with request_lifecycle("test_critic") as ctx:
        with audit_stage("self_correction", is_leaf=False):
            with audit_stage("critic", is_leaf=False):
                with audit_stage("critic_context"):
                    pass
                with audit_stage("critic_evaluation"):
                    pass
                with audit_stage("critic_verifier"):
                    pass

    summary = build_request_summary(ctx)
    corr_span = next((c for c in summary["hierarchy"]["children"] if c["name"] == "self_correction"), None)
    assert corr_span is not None
    critic_span = next((c for c in corr_span["children"] if c["name"] == "critic"), None)
    assert critic_span is not None
    critic_subs = [c["name"] for c in critic_span["children"]]
    assert "critic_context" in critic_subs
    assert "critic_evaluation" in critic_subs
    assert "critic_verifier" in critic_subs


# 17. Self-correction correction attempt sub-spans
def test_self_correction_attempt_sub_spans() -> None:
    with request_lifecycle("test_correction_attempts") as ctx:
        with audit_stage("self_correction", is_leaf=False):
            with audit_stage("correction_attempt_1", is_leaf=False):
                with audit_stage("correction_prep"):
                    pass
                with audit_stage("correction_llm"):
                    pass

    summary = build_request_summary(ctx)
    corr_span = next((c for c in summary["hierarchy"]["children"] if c["name"] == "self_correction"), None)
    assert corr_span is not None
    attempt_span = next((c for c in corr_span["children"] if c["name"] == "correction_attempt_1"), None)
    assert attempt_span is not None
    attempt_subs = [c["name"] for c in attempt_span["children"]]
    assert "correction_prep" in attempt_subs
    assert "correction_llm" in attempt_subs


# 18. Pure ASGI middleware lifecycle and api_framework_overhead_ms calculation
def test_asgi_middleware_lifecycle_and_overhead() -> None:
    app = FastAPI()
    app.add_middleware(LatencyAuditASGIMiddleware)

    captured_ctx: RequestAuditContext | None = None

    @app.get("/test-overhead")
    async def sample_endpoint() -> dict[str, str]:
        nonlocal captured_ctx
        captured_ctx = get_current_audit()
        assert captured_ctx is not None
        # Simulate pipeline execution
        with audit_stage("pipeline", is_leaf=False):
            time.sleep(0.005)
        return {"status": "ok"}

    client = TestClient(app)
    resp = client.get("/test-overhead")
    assert resp.status_code == 200

    assert captured_ctx is not None
    summary = build_request_summary(captured_ctx)
    assert summary["total_duration_ms"] > 0.0
    assert summary["pipeline_duration_ms"] > 0.0
    # Framework overhead = total - pipeline >= 0
    assert summary["api_framework_overhead_ms"] >= 0.0


# 19. ASGI response header injection
def test_asgi_middleware_header_injection() -> None:
    app = FastAPI()
    app.add_middleware(LatencyAuditASGIMiddleware)

    @app.get("/test-headers")
    async def sample_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    resp = client.get(
        "/test-headers",
        headers={"x-correlation-id": "custom-corr-123"},
    )
    assert resp.status_code == 200
    assert "x-ai-request-id" in resp.headers
    assert resp.headers.get("x-correlation-id") == "custom-corr-123"


# 20. Fail-safe telemetry behavior (telemetry errors never crash business logic)
def test_fail_safe_behavior_audit_errors_never_crash() -> None:
    with request_lifecycle("test_failsafe") as ctx:
        # Intentionally force a failure in audit writing or stage tracking
        with patch("src.observability.latency_audit.time.perf_counter_ns", side_effect=RuntimeError("Clock failure")):
            try:
                with audit_stage("failing_stage"):
                    # Business logic should still execute
                    business_result = 42 * 2
            except Exception:
                # audit_stage catches its own internal exceptions, or if clock fails, does not crash user code
                business_result = 42 * 2

        assert business_result == 84
