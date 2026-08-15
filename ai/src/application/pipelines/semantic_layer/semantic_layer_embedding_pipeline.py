from typing import Any

from src.infrastructure.semantic_layer.retrieval.semantic_index_builder import (
    SemanticIndexBuilder,
)


class SemanticLayerEmbeddingPipeline:
    """Create embeddings and build the index for an approved revision."""

    def __init__(
        self,
        index_builder: SemanticIndexBuilder,
    ) -> None:
        self._index_builder = index_builder

    def run(
        self,
        approved_layer: dict[str, Any],
    ) -> dict[str, Any]:

        metadata = approved_layer.get("metadata", {})

        if metadata.get("status") != "approved":
            raise ValueError(
                "Embedding and indexing require an approved "
                "Semantic Layer."
            )

        return self._index_builder.build(
            approved_layer
        )
