"""Tests for the internal semantic index sync endpoint."""
from __future__ import annotations

from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from main import app
from src.api.dependencies import get_semantic_repository


def test_sync_endpoint_triggers_sync_on_repository():
    mock_repo = MagicMock()
    mock_repo.sync_active_index.return_value = True
    mock_repo.indexed_revision_id = "REV-TEST"

    app.dependency_overrides[get_semantic_repository] = lambda: mock_repo
    try:
        client = TestClient(app)
        response = client.post("/internal/semantic/sync")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Success"
        assert data["rebuilt"] is True
        assert data["indexedRevisionId"] == "REV-TEST"
        mock_repo.sync_active_index.assert_called_once_with(force=True)
    finally:
        app.dependency_overrides.pop(get_semantic_repository, None)
