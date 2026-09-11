"""Unit tests for latency audit telemetry components."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.observability.audit_context import RequestAuditContext, get_current_audit
from src.observability.audit_logger import write_audit_event
from src.observability.audit_summary import build_request_summary
from src.observability.http_audit import build_http_audit_event, sanitize_url
from src.observability.latency_audit import (
    compute_hash,
    record_backend_call,
    record_llm_call,
    record_prompt,
    record_validation,
    request_lifecycle,
    stage as audit_stage,
)
from src.observability.ollama_audit import parse_ollama_metrics
from src.observability.system_metrics import capture_system_snapshot


def test_sanitize_url():
    raw = "http://localhost:5226/api/v1/Auth/token?token=secret123&other=safe"
    sanitized = sanitize_url(raw)
    assert "secret123" not in sanitized
    assert "[REDACTED]" in sanitized
    assert "other=safe" in sanitized


def test_http_audit_event():
    event = build_http_audit_event(
        request_id="req-123",
        stage="test_stage",
        method="GET",
        url="http://localhost:5226/api/v1/Branches/status?auth=topsecret",
        status_code=200,
        duration_ms=45.6,
        is_duplicate=True,
    )
    assert event["event"] == "backend_http_call"
    assert event["status_code"] == 200
    assert event["duration_ms"] == 45.6
    assert event["is_duplicate"] is True
    assert "topsecret" not in event["url"]


def test_system_snapshot():
    snap = capture_system_snapshot()
    assert "cpu_percent" in snap
    assert "ram_used_mb" in snap
    assert "process_rss_mb" in snap
    assert snap["process_rss_mb"] > 0


def test_ollama_metrics_parsing():
    raw_ollama = {
        "total_duration": 5_000_000_000,
        "load_duration": 1_200_000_000,
        "prompt_eval_duration": 800_000_000,
        "eval_duration": 3_000_000_000,
        "prompt_eval_count": 500,
        "eval_count": 150,
        "done_reason": "stop",
    }
    parsed = parse_ollama_metrics(
        raw_ollama,
        context_length=4096,
        max_output_tokens=2048,
        estimated_prompt_tokens=600,
    )
    assert parsed["is_cold_load"] is True
    assert parsed["prompt_eval_count"] == 500
    assert parsed["eval_count"] == 150
    assert parsed["prompt_tps"] == 625.0
    assert parsed["generation_tps"] == 50.0
    # Available budget: 4096 - 2048 + 2 = 2050; prompt 500 < 2050 -> not truncated
    assert parsed["prompt_truncated"] is False


def test_ollama_truncation_detection():
    raw_ollama = {
        "total_duration": 10_000_000_000,
        "load_duration": 50_000_000,
        "prompt_eval_duration": 2_000_000_000,
        "eval_duration": 7_950_000_000,
        "prompt_eval_count": 2050,
        "eval_count": 100,
    }
    # Available budget: 4096 - 2048 + 2 = 2050; estimated tokens was 5500
    parsed = parse_ollama_metrics(
        raw_ollama,
        context_length=4096,
        max_output_tokens=2048,
        estimated_prompt_tokens=5500,
    )
    assert parsed["prompt_truncated"] is True
    assert parsed["truncated_tokens_estimate"] == 3450


def test_request_lifecycle_and_summary(monkeypatch, tmp_path):
    log_file = tmp_path / "test_audit.jsonl"
    monkeypatch.setenv("LATENCY_AUDIT_LOG_FILE", str(log_file))

    with request_lifecycle(request_id="req-abc", correlation_id="corr-xyz") as ctx:
        assert get_current_audit() is ctx

        with audit_stage("stage_one", is_leaf=True):
            pass

        with audit_stage("stage_two", is_leaf=True):
            pass

        record_prompt(
            stage_name="sql_generation_prompt",
            model="qwen2.5-coder:7b",
            config_name="text_to_sql",
            prompt="SELECT * FROM branches",
            components={"question": 20},
        )

        record_validation(
            stage_name="deterministic_validation",
            sql="SELECT * FROM branches",
            is_valid=True,
            findings=[],
            duration_ms=12.5,
            sub_stages={"syntax_ms": 2.1, "schema_ms": 10.4},
        )

    # After context exit, audit context is cleared
    assert get_current_audit() is None

    # Check that log file was created with valid JSON lines
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 4

    events = [json.loads(line) for line in lines]
    event_types = [e.get("event") for e in events]
    assert "request_start" in event_types
    assert "stage_start" in event_types
    assert "stage_end" in event_types
    assert "prompt_assembly" in event_types
    assert "validation_complete" in event_types
    assert "request_summary" in event_types

    summary = next(e for e in events if e.get("event") == "request_summary")
    assert summary["request_id"] == "req-abc"
    assert summary["success"] is True
    assert "stage_one" in summary["leaf_stages_ms"]
    assert "stage_two" in summary["leaf_stages_ms"]
    assert summary["unaccounted_ms"] >= 0.0
