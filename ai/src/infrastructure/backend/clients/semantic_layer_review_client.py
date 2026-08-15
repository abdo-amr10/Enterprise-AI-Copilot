from src.application.dto.backend.semantic_layer.semantic_layer_review_request import (
    SemanticLayerReviewRequest,
)
from src.application.dto.backend.semantic_layer.semantic_layer_review_response import (
    SemanticLayerReviewResponse,
)
from src.infrastructure.backend.backend_http_client import BackendHttpClient


class SemanticLayerReviewClientImpl:
    """Submits Semantic Layer human-review decisions to the Backend."""

    def __init__(self, http_client: BackendHttpClient) -> None:
        """Initialize the Semantic Layer review client.

        Args:
            http_client: Shared HTTP client used to communicate
                with the Backend.
        """

        self._http_client = http_client

    def review(
        self,
        request: SemanticLayerReviewRequest,
    ) -> SemanticLayerReviewResponse:
        """Submit a human review decision for a Semantic Layer revision.

        Args:
            request: Review decision containing the Semantic Layer,
                revision, decision, and optional comments.

        Returns:
            The resulting revision status returned by the Backend.
        """

        payload = {
            "semanticLayerId": request.semantic_layer_id,
            "revisionId": request.revision_id,
            "decision": request.decision,
        }

        if request.comments is not None:
            payload["comments"] = request.comments

        response = self._http_client.post(
            "/api/v1/semantic-layer/review",
            payload,
        )

        return SemanticLayerReviewResponse(
            semantic_layer_id=response["semanticLayerId"],
            revision_id=response["revisionId"],
            status=response["status"],
            version=response.get("version"),
            approved_by=response.get("approvedBy"),
            approved_at=response.get("approvedAt"),
        )