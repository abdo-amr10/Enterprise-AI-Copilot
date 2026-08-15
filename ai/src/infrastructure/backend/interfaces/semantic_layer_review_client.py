from typing import Protocol

from src.application.dto.backend.semantic_layer.semantic_layer_review_request import (
    SemanticLayerReviewRequest,
)
from src.application.dto.backend.semantic_layer.semantic_layer_review_response import (
    SemanticLayerReviewResponse,
)


class SemanticLayerReviewClient(Protocol):
    """Defines the contract for submitting Semantic Layer reviews."""

    def review(
        self,
        request: SemanticLayerReviewRequest,
    ) -> SemanticLayerReviewResponse:
        """Submit a human review decision to the Backend.

        Args:
            request: Review decision and optional rejection comments.

        Returns:
            The resulting Semantic Layer revision status.
        """
        ...