"""Tests for the internal developer debug router and endpoints."""
from __future__ import annotations

from unittest.mock import patch
from fastapi.testclient import TestClient

from main import app
from src.observability.debug_runner import DebugResult


client = TestClient(app)


def test_debug_endpoint_accepts_valid_request_and_delegates_to_debug_runner() -> None:
    mock_result = DebugResult(
        requested_layer="retrieval",
        prerequisites=(),
        status="passed",
        metrics={"retrieval_latency_ms": 12.5, "retrieval_result_count": 3.0},
        tags={"prompt_name": "text_to_sql", "prompt_version": "sha256:1234"},
        local={"retrieval": [{"id": "doc1", "score": 0.9}]},
        stopping_point="retrieval",
    )

    with patch("src.api.routers.debug_router.DebugRunner.run", return_value=mock_result) as mock_run:
        response = client.post(
            "/internal/debug/run",
            json={"question": "Show all customers", "layer": "retrieval", "show_local_output": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "passed"
        assert data["requested_layer"] == "retrieval"
        assert data["stopping_point"] == "retrieval"
        assert data["metrics"]["retrieval_result_count"] == 3.0
        assert data["local"]["retrieval"][0]["id"] == "doc1"
        mock_run.assert_called_once_with(question="Show all customers", layer="retrieval")


def test_debug_endpoint_rejects_invalid_layer() -> None:
    response = client.post(
        "/internal/debug/run",
        json={"question": "Show all customers", "layer": "unsupported_xyz"},
    )
    assert response.status_code == 422  # Pydantic validation error for Literal


def test_debug_endpoint_respects_show_local_output_flag() -> None:
    mock_result = DebugResult(
        requested_layer="full",
        prerequisites=("request",),
        status="passed",
        metrics={"request_latency_ms": 100.0},
        tags={},
        local={"final_sql": "SELECT 1", "sensitive_stuff": "hidden"},
        stopping_point="production validated-SQL boundary",
    )

    with patch("src.api.routers.debug_router.DebugRunner.run", return_value=mock_result):
        response = client.post(
            "/internal/debug/run",
            json={"question": "Show all customers", "layer": "full", "show_local_output": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["local"] == {}


def test_debug_ui_serves_html() -> None:
    response = client.get("/internal/debug/ui")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Enterprise AI Copilot" in response.text
    assert "Developer Debugger" in response.text
