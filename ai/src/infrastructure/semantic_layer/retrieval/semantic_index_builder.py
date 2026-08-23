"""Processing-only semantic document embedding and vector-index construction."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from src.config.semantic_settings import SemanticSettings
from src.infrastructure.semantic_layer.retrieval.embedding_service import EmbeddingService
from src.infrastructure.semantic_layer.retrieval.semantic_document_builder import SemanticDocumentBuilder
from src.infrastructure.semantic_layer.retrieval.vector_index import VectorIndex


class SemanticIndexBuilder:
    """Build a derived index from an in-memory approved Backend revision."""

    def __init__(self, embedding_service: EmbeddingService, vector_index: VectorIndex,
                 document_builder: SemanticDocumentBuilder | None = None,
                 settings: SemanticSettings | None = None) -> None:
        self._embedding_service = embedding_service
        self._vector_index = vector_index
        self._document_builder = document_builder or SemanticDocumentBuilder()
        self._settings = settings or SemanticSettings()

    def build(self, layer: dict[str, Any]) -> dict[str, Any]:
        started = perf_counter()
        documents_started = perf_counter()
        documents = self._document_builder.build(layer)
        document_seconds = perf_counter() - documents_started
        embedding_started = perf_counter()
        embeddings = self._embedding_service.encode_documents([document["text"] for document in documents])
        embedding_seconds = perf_counter() - embedding_started
        metadata = layer["metadata"]
        index_started = perf_counter()
        index_metadata = {
            "index_version": self._settings.index_version,
            "semantic_layer_id": metadata["semantic_layer_id"],
            "revision_id": metadata["revision_id"],
            "embedding_model": self._embedding_service.model_name,
            "embedding_model_version": self._embedding_service.model_version,
            "embedding_dimension": self._embedding_service.embedding_dimension,
            "similarity_metric": self._settings.similarity_metric,
            "index_type": self._settings.index_type,
            "document_count": len(documents),
        }
        self._vector_index.build(documents, embeddings, index_metadata)
        self._vector_index.save()
        index_seconds = perf_counter() - index_started
        return {**index_metadata, "timings": {
            "document_preparation_seconds": document_seconds,
            "embedding_seconds": embedding_seconds,
            "index_build_seconds": index_seconds,
            "total_seconds": perf_counter() - started,
        }}
