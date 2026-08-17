from src.application.dto.backend.semantic_layer.semantic_layer_revision_response import (
    SemanticLayerRevisionResponse,
)
from src.application.dto.backend.semantic_layer.semantic_layer_revision_update_request import SemanticLayerRevisionUpdateRequest
from src.application.dto.backend.semantic_layer.semantic_layer_revision_update_response import SemanticLayerRevisionUpdateResponse
from src.application.dto.backend.semantic_layer.semantic_layer_review_request import SemanticLayerReviewRequest
from src.application.dto.backend.semantic_layer.semantic_layer_review_response import SemanticLayerReviewResponse
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

    def update_revision(self, request: SemanticLayerRevisionUpdateRequest) -> SemanticLayerRevisionUpdateResponse:
        response = self._http_client.put(
            f"/api/v1/semantic-layer/{request.semantic_layer_id}/revisions/{request.revision_id}",
            {"content": request.content},
        )
        return SemanticLayerRevisionUpdateResponse(
            semantic_layer_id=response["semanticLayerId"], revision_id=response["revisionId"],
            status=response["status"], message=response["message"],
        )

    def review_revision(self, request: SemanticLayerReviewRequest) -> SemanticLayerReviewResponse:
        payload = {"semanticLayerId": request.semantic_layer_id, "revisionId": request.revision_id, "decision": request.decision}
        if request.comments is not None:
            payload["comments"] = request.comments
        response = self._http_client.post("/api/v1/semantic-layer/review", payload)
        return SemanticLayerReviewResponse(
            semantic_layer_id=response["semanticLayerId"], revision_id=response["revisionId"], status=response["status"],
            version=response.get("version"), approved_by=response.get("approvedBy"), approved_at=response.get("approvedAt"),
        )
