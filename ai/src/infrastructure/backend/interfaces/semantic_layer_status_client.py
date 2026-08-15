from typing import Protocol

from src.application.dto.backend.semantic_layer.semantic_layer_status_response import (
    SemanticLayerStatusResponse,
)


class SemanticLayerStatusClient(Protocol):
    """Defines the contract for retrieving Semantic Layer status."""

    def get_status(
        self,
        semantic_layer_id: str,
    ) -> SemanticLayerStatusResponse:
        """Retrieve the current status of a Semantic Layer.

        Args:
            semantic_layer_id: Identifier of the Semantic Layer.

        Returns:
            The current Semantic Layer status.
        """
        ...