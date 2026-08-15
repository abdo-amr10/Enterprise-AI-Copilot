from typing import Protocol

from src.application.dto.backend.semantic_layer.semantic_layer_source_response import (
    SemanticLayerSourceResponse,
)


class SemanticLayerSourceClient(Protocol):
    """Defines the contract for retrieving Semantic Layer source files."""

    def get_source(
        self,
        file_id: str,
    ) -> SemanticLayerSourceResponse:
        """Retrieve a source file from the Backend.

        Args:
            file_id: Identifier of the source file.

        Returns:
            The requested source file metadata and content.

        Raises:
            ValueError: If the file ID is empty.
        """
        ...
        