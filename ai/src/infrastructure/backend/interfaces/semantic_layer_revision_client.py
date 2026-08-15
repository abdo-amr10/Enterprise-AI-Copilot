from typing import Protocol

from src.application.dto.backend.semantic_layer.semantic_layer_revision_response import (
    SemanticLayerRevisionResponse,
)
from src.application.dto.backend.semantic_layer.semantic_layer_revision_update_request import (
    SemanticLayerRevisionUpdateRequest,
)
from src.application.dto.backend.semantic_layer.semantic_layer_revision_update_response import (
    SemanticLayerRevisionUpdateResponse,
)
from src.application.dto.backend.semantic_layer.semantic_layer_review_request import (
    SemanticLayerReviewRequest,
)
from src.application.dto.backend.semantic_layer.semantic_layer_review_response import (
    SemanticLayerReviewResponse,
)


class SemanticLayerRevisionClient(Protocol):
    """Defines the application-level contract for Semantic Layer revisions."""

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
        """
        ...

    def update_revision(
        self,
        request: SemanticLayerRevisionUpdateRequest,
    ) -> SemanticLayerRevisionUpdateResponse:
        """Update and submit an edited Semantic Layer revision.

        Args:
            request: Revision update and submission data.

        Returns:
            Result of the revision update operation.
        """
        ...

    def review_revision(
        self,
        request: SemanticLayerReviewRequest,
    ) -> SemanticLayerReviewResponse:
        """Submit a human review decision for a Semantic Layer revision.

        Args:
            request: Human review decision and optional comments.

        Returns:
            Resulting revision review status.
        """
        ...