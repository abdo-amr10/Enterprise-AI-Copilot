from typing import Protocol

from src.application.dto.backend.semantic_layer.semantic_layer_status_response import (
    SemanticLayerStatusResponse,
)


class SemanticLayerStatusClient(Protocol):
    """Defines the contract for retrieving Semantic Layer status."""

    def get_status(self) -> SemanticLayerStatusResponse:
        """Retrieve the current status of a Semantic Layer.

        Args:
        Returns:
            The current Semantic Layer status.
        """
        ...
