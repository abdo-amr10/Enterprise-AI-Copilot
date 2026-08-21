"""FAISS exact cosine-similarity index with injectable derived-artifact storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from src.infrastructure.semantic_layer.retrieval.vector_index import VectorIndex


class FaissVectorIndex(VectorIndex):
    """Use normalized float32 vectors with ``faiss.IndexFlatIP``.

    The optional path persists only the derived index and its metadata; the
    approved Semantic Layer always remains an in-memory Backend input.
    """

    index_type = "faiss.IndexFlatIP"
    similarity_metric = "cosine"

    def __init__(self, artifact_path: str | Path | None = None) -> None:
        self._artifact_path = Path(artifact_path) if artifact_path else None
        self._index: Any | None = None
        self._documents: list[dict[str, Any]] = []
        self._metadata: dict[str, Any] = {}

    @staticmethod
    def _faiss() -> Any:
        try:
            import faiss
        except ImportError as error:
            raise RuntimeError(
                "FAISS is required for the production vector index. "
                "Install the 'faiss-cpu' project dependency."
            ) from error
        return faiss

    def build(self, documents: Sequence[dict[str, Any]], embeddings: Any, metadata: dict[str, Any]) -> None:
        vectors = np.asarray(embeddings, dtype=np.float32)
        if vectors.ndim != 2 or len(vectors) != len(documents):
            raise ValueError("Embeddings must be a 2-D matrix with one row per document.")
        if not len(documents):
            raise ValueError("Cannot build an index without semantic documents.")
        required_metadata = {
            "index_version", "semantic_layer_id", "revision_id",
            "embedding_model", "embedding_dimension", "document_count",
        }
        missing_metadata = required_metadata - metadata.keys()
        if missing_metadata:
            raise ValueError(f"Index metadata is missing: {sorted(missing_metadata)}")
        if metadata["embedding_dimension"] != vectors.shape[1]:
            raise ValueError("Index metadata embedding_dimension does not match vectors.")
        if metadata["document_count"] != len(documents):
            raise ValueError("Index metadata document_count does not match documents.")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise ValueError("Embeddings must not contain zero vectors.")
        vectors = vectors / norms
        faiss = self._faiss()
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        self._index = index
        self._documents = list(documents)
        self._metadata = {
            **metadata,
            "index_type": self.index_type,
            "similarity_metric": self.similarity_metric,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def search(self, query_embedding: Any, top_k: int) -> list[dict[str, Any]]:
        if self._index is None:
            self.load()
        if not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive integer.")
        query = np.asarray(query_embedding, dtype=np.float32).reshape(1, -1)
        if query.shape[1] != self._index.d:
            raise ValueError(f"Embedding dimension mismatch: index={self._index.d}, query={query.shape[1]}")
        norm = np.linalg.norm(query)
        if norm == 0:
            raise ValueError("Query embedding must not be a zero vector.")
        scores, indices = self._index.search(query / norm, top_k)
        return [
            {**self._documents[index], "score": float(scores[0][position])}
            for position, index in enumerate(indices[0]) if index >= 0
        ]

    def save(self) -> None:
        if self._artifact_path is None:
            return
        if self._index is None:
            raise ValueError("Cannot save an empty vector index.")
        self._artifact_path.parent.mkdir(parents=True, exist_ok=True)
        self._faiss().write_index(self._index, str(self._artifact_path))
        self._metadata_path().write_text(json.dumps({"metadata": self._metadata, "documents": self._documents}, ensure_ascii=False), encoding="utf-8")

    def load(self) -> None:
        if self._artifact_path is None:
            raise ValueError("No vector-index artifact path was configured.")
        sidecar = self._metadata_path()
        if not self._artifact_path.exists() or not sidecar.exists():
            raise FileNotFoundError("FAISS index artifact or metadata sidecar is missing.")
        stored = json.loads(sidecar.read_text(encoding="utf-8"))
        self._index = self._faiss().read_index(str(self._artifact_path))
        self._documents = stored["documents"]
        self._metadata = stored["metadata"]

    def validate_metadata(self, expected: dict[str, Any]) -> None:
        if self._index is None:
            self.load()
        for key, value in expected.items():
            if self._metadata.get(key) != value:
                raise ValueError(f"Semantic index metadata mismatch for '{key}'; rebuild it.")

    def _metadata_path(self) -> Path:
        assert self._artifact_path is not None
        return self._artifact_path.with_suffix(self._artifact_path.suffix + ".metadata.json")
