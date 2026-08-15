from src.application.dto.backend.semantic_layer.semantic_layer_revision_update_request import (
    SemanticLayerRevisionUpdateRequest,
)
from src.application.dto.backend.semantic_layer.semantic_layer_revision_update_response import (
    SemanticLayerRevisionUpdateResponse,
)
from src.infrastructure.backend.backend_http_client import BackendHttpClient


class SemanticLayerRevisionUpdateClientImpl:
    """Updates and submits Semantic Layer revisions through the Backend API."""

    def __init__(self, http_client: BackendHttpClient) -> None:
        """Initialize the Semantic Layer revision update client.

        Args:
            http_client: Shared HTTP client used to communicate
                with the Backend.
        """

        self._http_client = http_client

    def update(
        self,
        request: SemanticLayerRevisionUpdateRequest,
    ) -> SemanticLayerRevisionUpdateResponse:
        """Update a Semantic Layer revision and submit it for validation.

        Args:
            request: Revision update containing the Semantic Layer,
                revision, and edited content.

        Returns:
            Result of the revision update operation.
        """

        payload = {
            "content": request.content,
        }

        response = self._http_client.put(
            f"/api/v1/semantic-layer/"
            f"{request.semantic_layer_id}/revisions/"
            f"{request.revision_id}",
            payload,
        )

        return SemanticLayerRevisionUpdateResponse(
            semantic_layer_id=response["semanticLayerId"],
            revision_id=response["revisionId"],
            status=response["status"],
            message=response["message"],
        )