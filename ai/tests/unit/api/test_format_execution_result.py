"""Unit tests for the ExecutionResult normalization in the format-execution-result endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.post_query_dependencies import get_post_query_response_formatter
from src.application.services.post_query_response.post_query_response_formatter import (
    PostQueryResponseFormatter,
)
from src.config.post_query_response_settings import PostQueryResponseSettings
from main import app


@pytest.fixture
def client() -> TestClient:
    formatter = PostQueryResponseFormatter(settings=PostQueryResponseSettings(max_inline_rows=100))
    app.dependency_overrides[get_post_query_response_formatter] = lambda: formatter
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_format_execution_result_with_empty_list(client: TestClient) -> None:
    response = client.post(
        "/internal/copilot/format-execution-result",
        json={
            "question": "Show revenue",
            "executionResult": [],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Success"
    assert data["presentationType"] == "Empty"
    assert data["rowCount"] == 0
    assert data["columns"] == []
    assert data["rows"] == []
    assert "couldn’t find" in data["text"]
    assert data["excelExport"] is None
    assert data["heroMetric"] is None
    assert data["kpiCards"] is None




def test_format_execution_result_with_single_row_and_single_column(client: TestClient) -> None:
    response = client.post(
        "/internal/copilot/format-execution-result",
        json={
            "question": "What is the total revenue?",
            "executionResult": [{"TotalRevenue": 145000.0}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Success"
    assert data["presentationType"] == "SingleValue"
    assert data["rowCount"] == 1
    assert data["columns"] == ["TotalRevenue"]
    assert data["rows"] == [[145000.0]]
    assert "TotalRevenue is 145000.0" in data["text"]


def test_format_execution_result_with_multi_row_and_multiple_columns(client: TestClient) -> None:
    response = client.post(
        "/internal/copilot/format-execution-result",
        json={
            "question": "List top customers",
            "executionResult": [
                {"Id": 1, "Name": "Alice", "IsActive": True, "Balance": 250.75, "Joined": "2026-01-15T00:00:00Z"},
                {"Id": 2, "Name": "Bob", "IsActive": False, "Balance": 0.0, "Joined": "2026-02-20T00:00:00Z"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Success"
    assert data["presentationType"] == "Table"
    assert data["rowCount"] == 2
    assert data["columns"] == ["Id", "Name", "IsActive", "Balance", "Joined"]
    assert len(data["rows"]) == 2
    assert data["rows"][0] == [1, "Alice", True, 250.75, "2026-01-15T00:00:00Z"]
    assert data["rows"][1] == [2, "Bob", False, 0.0, "2026-02-20T00:00:00Z"]


def test_format_execution_result_with_null_values(client: TestClient) -> None:
    response = client.post(
        "/internal/copilot/format-execution-result",
        json={
            "question": "Show loans",
            "executionResult": [
                {"LoanId": 101, "EndDate": None, "Status": "Active"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Success"
    assert data["columns"] == ["LoanId", "EndDate", "Status"]
    assert data["rows"] == [[101, None, "Active"]]


def test_format_execution_result_with_inconsistent_sparse_keys(client: TestClient) -> None:
    response = client.post(
        "/internal/copilot/format-execution-result",
        json={
            "question": "Show details",
            "executionResult": [
                {"ColA": 10, "ColB": "X"},
                {"ColB": "Y", "ColC": True},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Success"
    assert data["columns"] == ["ColA", "ColB", "ColC"]
    assert data["rows"][0] == [10, "X", None]
    assert data["rows"][1] == [None, "Y", True]


def test_format_execution_result_with_structured_contract(client: TestClient) -> None:
    response = client.post(
        "/internal/copilot/format-execution-result",
        json={
            "question": "Show customers",
            "executionResult": {
                "status": "Success",
                "columns": ["Id", "Name"],
                "rows": [[1, "Charlie"], [2, "Dave"]],
                "rowCount": 2,
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Success"
    assert data["presentationType"] == "Table"
    assert data["columns"] == ["Id", "Name"]
    assert data["rows"] == [[1, "Charlie"], [2, "Dave"]]


def test_format_execution_result_invalid_request_rejected(client: TestClient) -> None:
    # Missing question (empty string violates min_length=1)
    response = client.post(
        "/internal/copilot/format-execution-result",
        json={
            "question": "",
            "executionResult": [],
        },
    )
    assert response.status_code == 422


def test_format_execution_result_pydantic_types_and_camelcase_serialization(client: TestClient) -> None:
    response = client.post(
        "/internal/copilot/format-execution-result",
        json={
            "question": "Show revenue",
            "executionResult": [
                {"Department": "Sales", "Revenue": 50000.0},
                {"Department": "Marketing", "Revenue": 20000.0},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["status"], str)
    assert isinstance(data["presentationType"], str)
    assert isinstance(data["rowCount"], int)
    assert isinstance(data["columns"], list)
    assert isinstance(data["rows"], list)
    assert isinstance(data["text"], str)

    # Check TableData nested structure
    assert data["tableData"] is not None
    assert isinstance(data["tableData"]["totalRows"], int)
    assert data["tableData"]["totalRows"] == 2
    assert data["tableData"]["columns"] == ["Department", "Revenue"]

    # Check ExcelExport nested structure
    assert data["excelExport"] is not None
    assert isinstance(data["excelExport"]["available"], bool)
    assert data["excelExport"]["available"] is True
    assert isinstance(data["excelExport"]["fileName"], str)
    assert data["excelExport"]["fileName"].endswith(".xlsx")

