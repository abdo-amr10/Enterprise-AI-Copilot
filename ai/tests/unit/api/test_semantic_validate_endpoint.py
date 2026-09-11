from __future__ import annotations

from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers import semantic_router
from src.api.generation_validation_dependencies import get_semantic_validation_pipeline
from src.application.pipelines.semantic_layer.semantic_layer_validation_pipeline import (
    SemanticLayerValidationPipeline,
)


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(semantic_router.router)
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _valid_draft() -> dict:
    return {
        "metadata": {
            "semantic_layer_id": "sl-001",
            "revision_id": "rev-001",
            "base_revision_id": None,
            "trigger_type": "FullRebuild",
            "status": "initial_draft",
            "validated": False,
            "human_review_required": True,
        },
        "entities": [
            {
                "id": "e_users",
                "name": "Users",
                "table_name": "users",
                "primary_key": ["user_id"],
                "description": "User entity",
            }
        ],
        "relationships": [],
        "measures": [],
        "dimensions": [],
        "business_rules": [],
        "validation_issues": [],
    }


def _valid_schema() -> dict:
    return {
        "tables": {
            "users": {
                "columns": {
                    "user_id": {"data_type": "int", "is_primary_key": True}
                },
                "primary_keys": ["user_id"],
            }
        },
        "relationships": [],
    }


def test_validate_acknowledgement_mode(client: TestClient) -> None:
    response = client.post("/internal/semantic/validate", json={"revisionId": "rev-123"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Success"
    assert data["revisionId"] == "rev-123"
    assert data["validation"] == {
        "status": "passed",
        "mode": "backend-acknowledgement",
    }


def test_validate_with_draft_and_schema_passes(app: FastAPI, client: TestClient) -> None:
    mock_pipeline = Mock(spec=SemanticLayerValidationPipeline)
    validated_draft = _valid_draft()
    validated_draft["metadata"]["validated"] = True
    validated_draft["metadata"]["status"] = "validated"
    mock_validation = {
        "status": "passed",
        "errors": [],
        "warnings": [],
        "checks": {"structure": "passed", "relationships": "passed", "duplicates": "passed"},
    }
    mock_pipeline.run.return_value = (validated_draft, mock_validation)

    app.dependency_overrides[get_semantic_validation_pipeline] = lambda: mock_pipeline
    try:
        response = client.post(
            "/internal/semantic/validate",
            json={
                "draft": _valid_draft(),
                "schema": _valid_schema(),
                "relationships": [],
                "documentation": "User documentation",
                "businessGlossary": "User glossary",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Success"
        assert data["draft"]["metadata"]["status"] == "validated"
        assert data["validation"]["status"] == "passed"
        mock_pipeline.run.assert_called_once_with(
            draft=_valid_draft(),
            schema=_valid_schema(),
            relationships=[],
            has_semantic_context=True,
            documentation="User documentation",
            glossary="User glossary",
        )
    finally:
        app.dependency_overrides.clear()


def test_validate_missing_schema_when_draft_supplied(client: TestClient) -> None:
    response = client.post(
        "/internal/semantic/validate",
        json={"draft": _valid_draft()},
    )
    assert response.status_code == 422
    assert "draft and schema must be supplied together" in response.json()["detail"]


def test_validate_missing_draft_when_schema_supplied(client: TestClient) -> None:
    response = client.post(
        "/internal/semantic/validate",
        json={"schema": _valid_schema()},
    )
    assert response.status_code == 422
    assert "draft and schema must be supplied together" in response.json()["detail"]


def test_validate_missing_both_revision_id_and_draft_schema(client: TestClient) -> None:
    response = client.post(
        "/internal/semantic/validate",
        json={},
    )
    assert response.status_code == 422
    assert "revisionId or draft plus schema is required" in response.json()["detail"]


def test_semantic_validation_pipeline_dependency_instantiation() -> None:
    pipeline = get_semantic_validation_pipeline()
    assert isinstance(pipeline, SemanticLayerValidationPipeline)
