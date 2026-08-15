from unittest.mock import Mock

from src.infrastructure.backend.backend_http_client import BackendHttpClient
from src.infrastructure.backend.clients.semantic_layer_status_client import (
    SemanticLayerStatusClientImpl,
)


def test_get_status() -> None:
    http_client = Mock(spec=BackendHttpClient)

    http_client.get.return_value = {
        "status": "Approved",
        "version": "v1",
        "buildTimestamp": "2026-08-15T00:00:00Z",
        "lastRegenerationType": "FullRebuild",
    }

    client = SemanticLayerStatusClientImpl(http_client)

    response = client.get_status()

    print(response)

    assert response.status == "Approved"
    assert response.version == "v1"
    assert response.build_timestamp == "2026-08-15T00:00:00Z"
    assert response.last_regeneration_type == "FullRebuild"

    http_client.get.assert_called_once_with(
        "/api/v1/semantic-layer/status"
    )
    