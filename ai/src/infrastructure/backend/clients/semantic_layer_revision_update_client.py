from src.application.dto.backend.semantic_layer.semantic_layer_revision_update_response import (
    SemanticLayerRevisionUpdateResponse,
)
from src.infrastructure.backend.backend_http_client import BackendHttpClient


class SemanticLayerSubmitClientImpl:
    """Submits an already edited Semantic Layer revision for validation."""

    def __init__(self, http_client: BackendHttpClient) -> None:
        """Initialize the Semantic Layer revision update client.

        Args:
            http_client: Shared HTTP client used to communicate
                with the Backend.
        """

        self._http_client = http_client

    def submit(
        self,
        semantic_layer_id: str,
        revision_id: str,
    ) -> SemanticLayerRevisionUpdateResponse:
        """Submit a Semantic Layer revision for validation.

        Args:
            semantic_layer_id: Identifier of the Semantic Layer.
            revision_id: Identifier of the edited revision.

        Returns:
            Result of the revision update operation.
        """

        if not semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")
        if not revision_id.strip():
            raise ValueError("revision_id cannot be empty.")

        response = self._http_client.post(
            f"/api/v1/semantic-layer/revisions/{revision_id}/submit",
            {},
        )

        return SemanticLayerRevisionUpdateResponse(
            semantic_layer_id=response["semanticLayerId"],
            revision_id=response["revisionId"],
            status=response["status"],
            message=response["message"],
        )
