from typing import Protocol

from src.application.dto.backend.semantic_layer.semantic_layer_revision_update_response import (
    SemanticLayerRevisionUpdateResponse,
)


class SemanticLayerSubmitClient(Protocol):
    """Defines the contract for submitting edited revisions."""

    def submit(
        self,
        semantic_layer_id: str,
        revision_id: str,
    ) -> SemanticLayerRevisionUpdateResponse:
        """Submit an edited Semantic Layer revision.

        Args:
            semantic_layer_id: Identifier of the Semantic Layer.
            revision_id: Identifier of the edited revision.

        Returns:
            Submission result from the Backend.
        """
        ...
        
