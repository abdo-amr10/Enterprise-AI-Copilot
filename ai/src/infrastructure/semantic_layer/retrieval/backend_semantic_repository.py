"""Vector retrieval adapter whose authoritative semantic state is the Backend."""

from __future__ import annotations

from typing import Any

from src.application.pipelines.semantic_layer.semantic_layer_embedding_pipeline import (
    SemanticLayerEmbeddingPipeline,
)
from src.config.semantic_settings import SemanticSettings
from src.infrastructure.backend.backend_semantic_client import BackendSemanticClient
from src.infrastructure.semantic_layer.retrieval.embedding_service import EmbeddingService
from src.infrastructure.semantic_layer.retrieval.faiss_vector_index import FaissVectorIndex
from src.infrastructure.semantic_layer.retrieval.semantic_index_builder import SemanticIndexBuilder


class BackendSemanticRepository:
    """Retrieve from an in-memory FAISS index of the approved Backend revision.

    The Backend remains the source of truth for the active revision.  The index
    is a disposable derived cache: it is rebuilt only when that revision changes
    and is never a fallback source of semantic state.
    """

    def __init__(
        self,
        client: BackendSemanticClient | None = None,
        embedding_service: EmbeddingService | None = None,
        vector_index: FaissVectorIndex | None = None,
        settings: SemanticSettings | None = None,
    ) -> None:
        self._client = client or BackendSemanticClient()
        self._settings = settings or SemanticSettings()
        self._embedding_service = embedding_service or EmbeddingService(
            self._settings.production_embedding_model_path,
            model_name=self._settings.production_embedding_model_name,
            device=self._settings.embedding_device,
            batch_size=self._settings.embedding_batch_size,
            normalize=self._settings.normalize_embeddings,
        )
        self._vector_index = vector_index or FaissVectorIndex()
        self._indexing_pipeline = SemanticLayerEmbeddingPipeline(
            SemanticIndexBuilder(
                self._embedding_service,
                self._vector_index,
                settings=self._settings,
            )
        )
        self._cached_revision_id: str | None = None
        self._cached_layer: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        """Return the active approved revision, refreshing cache on revision change."""

        status = self._client.get_status()
        if status.get("status") != "Approved":
            raise ValueError("Runtime retrieval requires a Backend-approved semantic revision.")
        revision_id = status.get("revisionId")
        if not isinstance(revision_id, str) or not revision_id:
            raise ValueError("Backend semantic status did not provide revisionId.")

        if self._cached_layer is not None and self._cached_revision_id == revision_id:
            return self._cached_layer

        layer = self._client.load_revision(revision_id)
        metadata = layer.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("Approved Backend semantic revision has no metadata.")
        if metadata.get("revision_id") != revision_id:
            raise ValueError("Backend revision identity did not match the active revision.")
        self._cached_revision_id = revision_id
        self._cached_layer = layer
        return layer

    def retrieve(self, question: str, top_k: int = 8) -> list[dict[str, Any]]:
        """Return top-k semantic documents using the configured embedding model."""

        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be non-empty.")
        if not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive integer.")

        layer = self.load()
        revision_id = layer["metadata"]["revision_id"]
        if self._cached_revision_id != revision_id:
            # Defensive only: ``load`` sets both values together.
            raise RuntimeError("Active semantic revision cache is inconsistent.")

        if getattr(self, "_indexed_revision_id", None) != revision_id:
            self._indexing_pipeline.run(layer)
            self._indexed_revision_id = revision_id

        results = self._vector_index.search(
            self._embedding_service.encode_query(question),
            top_k,
        )
        return [
            {
                **result,
                "type": result["object_type"],
                "semanticLayerId": result["semantic_layer_id"],
                "revisionId": result["revision_id"],
            }
            for result in results
        ]
