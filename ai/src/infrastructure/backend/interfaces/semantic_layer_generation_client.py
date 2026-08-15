from typing import Protocol

from src.application.dto.backend.semantic_layer.semantic_layer_generation_response import (
    SemanticLayerGenerationResponse,
)
from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)


class SemanticLayerGenerationClient(Protocol):
    """Defines the contract for triggering Semantic Layer generation."""

    def generate_draft(
        self,
        request: SemanticLayerGenerationRequest,
    ) -> SemanticLayerGenerationResponse:
        """Trigger Semantic Layer draft generation.

        Args:
            request: Generation trigger configuration.

        Returns:
            Information about the generated Semantic Layer revision.

        Raises:
            ValueError: If the request is invalid.
        """
        ...