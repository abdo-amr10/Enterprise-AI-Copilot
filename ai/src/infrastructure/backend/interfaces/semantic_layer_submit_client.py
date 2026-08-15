from typing import Protocol

from src.application.dto.backend.semantic_layer.semantic_layer_revision_update_response import (
    SemanticLayerSubmitResponse,
)


class SemanticLayerSubmitClient(Protocol):
    """Defines the contract for submitting edited revisions."""

    def submit(
        self,
        revision_id: str,
    ) -> SemanticLayerSubmitResponse:
        """Submit an edited Semantic Layer revision.

        Args:
            revision_id: Identifier of the edited revision.

        Returns:
            Submission result from the Backend.
        """
        ...
        
