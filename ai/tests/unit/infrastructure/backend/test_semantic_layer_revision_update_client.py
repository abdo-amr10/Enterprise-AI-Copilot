"""Unit tests for the SemanticLayerSubmitClient route and behavior."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.infrastructure.backend.backend_http_client import BackendHttpClient
from src.infrastructure.backend.clients.semantic_layer_revision_update_client import (
    SemanticLayerSubmitClientImpl,
)


def test_submit_calls_canonical_backend_route_without_layer_id_path() -> None:
    http_client = Mock(spec=BackendHttpClient)
    http_client.post.return_value = {
        "semanticLayerId": "sl-001",
        "revisionId": "rev-001",
        "status": "Submitted",
        "message": "Revision submitted for validation.",
    }

    client = SemanticLayerSubmitClientImpl(http_client)
    response = client.submit(semantic_layer_id="sl-001", revision_id="rev-001")

    assert response.status == "Submitted"
    assert response.revision_id == "rev-001"
    http_client.post.assert_called_once_with(
        "/api/v1/semantic-layer/revisions/rev-001/submit",
        {},
    )


def test_submit_validates_non_empty_identifiers() -> None:
    http_client = Mock(spec=BackendHttpClient)
    client = SemanticLayerSubmitClientImpl(http_client)

    with pytest.raises(ValueError, match="semantic_layer_id cannot be empty"):
        client.submit(semantic_layer_id="", revision_id="rev-001")

    with pytest.raises(ValueError, match="revision_id cannot be empty"):
        client.submit(semantic_layer_id="sl-001", revision_id="")
