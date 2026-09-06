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
        import threading
        self._lock = threading.RLock()
        self._cached_revision_id: str | None = None
        self._cached_layer: dict[str, Any] | None = None
        self._indexed_revision_id: str | None = None

    @property
    def indexed_revision_id(self) -> str | None:
        """Return the revision ID currently indexed in memory."""
        return self._indexed_revision_id

    def is_ready(self) -> bool:
        """Return True if the repository has a loaded layer and an active vector index in memory."""
        if (
            self._cached_layer is None
            or self._cached_revision_id is None
            or self._indexed_revision_id is None
            or self._cached_revision_id != self._indexed_revision_id
        ):
            return False
        if getattr(self._vector_index, "_index", None) is not None:
            return True
        if hasattr(self._vector_index, "documents") and self._vector_index.documents:
            return True
        if hasattr(self._vector_index, "search"):
            return True
        return False

    def ensure_initialized(self) -> None:
        """Prepare in-memory semantic index outside or prior to normal question execution."""
        if self.is_ready():
            return
        with self._lock:
            if self.is_ready():
                return
            self.sync_active_index(force=False)

    def sync_active_index(self, force: bool = False) -> bool:
        """Synchronize the in-memory FAISS index with the active Backend revision.

        Fetches status, loads the approved revision if unindexed or changed, attempts to
        download and restore the compiled artifact ZIP from Backend, or builds locally only
        on explicit 404, and atomically updates in-memory state.

        Args:
            force: If True, re-indexes even if revision_id matches current index.

        Returns:
            True if a new index was built or loaded, False if already up-to-date or unavailable.
        """
        with self._lock:
            try:
                try:
                    status = self._client.get_status(force=True)
                except TypeError:
                    status = self._client.get_status()
            except Exception:
                return False

            if not isinstance(status, dict) or status.get("status") != "Approved":
                return False
            revision_id = status.get("revisionId")
            if not isinstance(revision_id, str) or not revision_id:
                return False

            if not force and self.is_ready() and self._indexed_revision_id == revision_id:
                return False

            # Step 1: Fetch authoritative layer definition
            try:
                layer = self._client.load_revision(revision_id)
            except Exception:
                return False

            metadata = layer.get("metadata") if isinstance(layer, dict) else None
            if not isinstance(metadata, dict) or metadata.get("revision_id") != revision_id:
                return False

            # Step 2: Attempt artifact download from Backend if client supports it
            artifact_zip: bytes | None = None
            if hasattr(self._client, "download_index_artifact"):
                try:
                    artifact_zip = self._client.download_index_artifact(revision_id)
                except Exception:
                    # Operational failure (500, timeout, network). Do NOT rebuild locally!
                    return False

            if artifact_zip is not None:
                # HTTP 200 OK: Valid artifact bundle returned from Backend
                try:
                    new_index = FaissVectorIndex()
                    new_index.load_from_zip_bytes(artifact_zip, expected_revision_id=revision_id)
                    # Atomic state swap
                    self._vector_index = new_index
                    self._cached_layer = layer
                    self._cached_revision_id = revision_id
                    self._indexed_revision_id = revision_id
                    return True
                except Exception:
                    # Malformed or incompatible artifact: reject, do not partially mutate state
                    return False

            # Step 3: Explicit 404 (artifact missing) or fallback: build locally via CPU
            try:
                new_index = FaissVectorIndex() if isinstance(self._vector_index, FaissVectorIndex) else self._vector_index
                builder = SemanticIndexBuilder(
                    self._embedding_service,
                    new_index,
                    settings=self._settings,
                )
                pipeline = SemanticLayerEmbeddingPipeline(builder)
                pipeline.run(layer)

                # If artifact upload is supported, upload newly built bundle
                if hasattr(new_index, "export_bundle_bytes") and hasattr(self._client, "upload_index_artifact"):
                    try:
                        faiss_bytes, index_meta_json, doc_meta_json = new_index.export_bundle_bytes()
                        self._client.upload_index_artifact(
                            revision_id=revision_id,
                            faiss_bytes=faiss_bytes,
                            index_metadata_json=index_meta_json,
                            document_metadata_json=doc_meta_json,
                        )
                    except Exception:
                        # Upload failure (e.g. peer already published or network glitch).
                        # Index is still valid in local memory.
                        pass

                # Atomic state swap
                self._vector_index = new_index
                self._cached_layer = layer
                self._cached_revision_id = revision_id
                self._indexed_revision_id = revision_id
                return True
            except Exception:
                return False

    def load(self, allow_cold_start: bool = True) -> dict[str, Any]:
        """Return the active approved revision from memory, initializing only if not yet loaded."""
        if self._cached_layer is not None:
            return self._cached_layer

        with self._lock:
            if self._cached_layer is not None:
                return self._cached_layer
            if not allow_cold_start:
                raise RuntimeError(
                    "SemanticLayerNotReady: In-memory semantic layer is not initialized. "
                    "Cold initialization must not run during a user request; "
                    "ensure warmup has completed or trigger /internal/semantic/sync."
                )
            self.ensure_initialized()
            if self._cached_layer is not None:
                return self._cached_layer
            raise ValueError("Runtime retrieval requires a Backend-approved semantic revision.")

    def retrieve(
        self,
        question: str,
        top_k: int = 8,
        allow_cold_start: bool = True,
    ) -> list[dict[str, Any]]:
        """Return top-k semantic documents using the configured embedding model (0 Backend HTTP calls)."""
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be non-empty.")
        if not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive integer.")

        if not self.is_ready():
            with self._lock:
                if not self.is_ready():
                    if not allow_cold_start:
                        raise RuntimeError(
                            "SemanticLayerNotReady: In-memory semantic index is not initialized. "
                            "Cold initialization must not run during a user request; "
                            "ensure warmup has completed or trigger /internal/semantic/sync."
                        )
                    self.ensure_initialized()

        import time
        from src.observability.audit_logger import write_audit_event
        from src.observability.audit_context import get_current_audit

        t_emb = time.perf_counter()
        query_vector = self._embedding_service.encode_query(question)
        emb_dur_ms = (time.perf_counter() - t_emb) * 1000.0

        ctx = get_current_audit()
        req_id = ctx.request_id if ctx else None
        if ctx:
            ctx.record_leaf_duration("embedding_generation", emb_dur_ms)

        try:
            write_audit_event({
                "event": "embedding_complete",
                "request_id": req_id,
                "stage": "retrieval",
                "model_name": self._embedding_service.model_name,
                "dimension": self._embedding_service.embedding_dimension,
                "device": self._embedding_service.device,
                "input_chars": len(question),
                "duration_ms": round(emb_dur_ms, 2),
            })
        except Exception:
            pass

        t_faiss = time.perf_counter()
        results = self._vector_index.search(
            query_vector,
            top_k,
        )
        faiss_dur_ms = (time.perf_counter() - t_faiss) * 1000.0

        if ctx:
            ctx.record_leaf_duration("faiss_vector_search", faiss_dur_ms)

        try:
            write_audit_event({
                "event": "vector_search_complete",
                "request_id": req_id,
                "stage": "retrieval",
                "top_k": top_k,
                "results_count": len(results),
                "duration_ms": round(faiss_dur_ms, 2),
            })
        except Exception:
            pass
        return [
            {
                **result,
                "type": result.get("object_type") or result.get("type"),
                "object_type": result.get("object_type") or result.get("type"),
                "semanticLayerId": result.get("semantic_layer_id") or result.get("semanticLayerId"),
                "revisionId": result.get("revision_id") or result.get("revisionId"),
            }
            for result in results
        ]
