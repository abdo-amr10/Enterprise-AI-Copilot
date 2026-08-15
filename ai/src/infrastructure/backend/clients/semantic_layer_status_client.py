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

    def get_status(
        self,
        semantic_layer_id: str,
    ) -> SemanticLayerStatusResponse:
        """Retrieve the current status of a Semantic Layer.

        Args:
            semantic_layer_id: Identifier of the Semantic Layer.

        Returns:
            The current Semantic Layer status.

        Raises:
            ValueError: If the Semantic Layer ID is empty.
        """

        if not semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")

        response = self._http_client.get(
            f"/api/v1/semantic-layer/"
            f"{semantic_layer_id}/status"
        )

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