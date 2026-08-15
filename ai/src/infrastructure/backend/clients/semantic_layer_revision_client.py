from src.application.dto.backend.semantic_layer.semantic_layer_revision_response import (
    SemanticLayerRevisionResponse,
)
from src.infrastructure.backend.backend_http_client import BackendHttpClient


class SemanticLayerRevisionClientImpl:
    """Retrieves Semantic Layer revisions from the Backend API."""

    def __init__(self, http_client: BackendHttpClient) -> None:
        """Initialize the Semantic Layer revision client.

        Args:
            http_client: Shared HTTP client used to communicate
                with the Backend.
        """

        self._http_client = http_client

    def get_revision(
        self,
        semantic_layer_id: str,
        revision_id: str,
    ) -> SemanticLayerRevisionResponse:
        """Retrieve a Semantic Layer revision from the Backend.

        Args:
            semantic_layer_id: Identifier of the Semantic Layer.
            revision_id: Identifier of the requested revision.

        Returns:
            The requested Semantic Layer revision.

        Raises:
            ValueError: If either identifier is empty.
        """

        if not semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")

        if not revision_id.strip():
            raise ValueError("revision_id cannot be empty.")

        response = self._http_client.get(
            f"/api/v1/semantic-layer/"
            f"{semantic_layer_id}/revisions/{revision_id}"
        )

        return SemanticLayerRevisionResponse(
            semantic_layer_id=response["semanticLayerId"],
            revision_id=response["revisionId"],
            status=response["status"],
            version=response.get("version"),
            build_timestamp=response["buildTimestamp"],
            last_regeneration_type=response["lastRegenerationType"],
            content=response["content"],
            created_at=response["createdAt"],
        )