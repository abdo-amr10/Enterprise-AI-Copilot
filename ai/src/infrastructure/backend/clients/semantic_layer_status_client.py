from src.application.dto.backend.semantic_layer.semantic_layer_status_response import (
    SemanticLayerStatusResponse,
)
from src.infrastructure.backend.backend_http_client import BackendHttpClient


class SemanticLayerStatusClientImpl:
    """Retrieves the current Semantic Layer status from the Backend."""

    def __init__(self, http_client: BackendHttpClient) -> None:
        """Initialize the Semantic Layer status client.

        Args:
            http_client: Shared HTTP client used to communicate
                with the Backend.
        """

        self._http_client = http_client

    def get_status(self) -> SemanticLayerStatusResponse:
        """Retrieve the current status of a Semantic Layer.

        Args:
        Returns:
            The current Semantic Layer status.

        """

        response = self._http_client.get("/api/v1/semantic-layer/status")

        return SemanticLayerStatusResponse(
            semantic_layer_id=response["semanticLayerId"],
            revision_id=response["revisionId"],
            status=response["status"],
            version=response["version"],
            build_timestamp=response["buildTimestamp"],
            last_regeneration_type=response[
                "lastRegenerationType"
            ],
        )
