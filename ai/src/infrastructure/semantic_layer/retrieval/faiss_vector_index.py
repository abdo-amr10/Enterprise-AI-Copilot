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

    def export_bundle_bytes(self) -> tuple[bytes, str, str]:
        """Export the index and its metadata as in-memory bundle components.

        Returns:
            Tuple of (faiss_binary_bytes, index_metadata_json, document_metadata_json).

        Raises:
            ValueError: If index or documents are empty.
        """
        if self._index is None:
            raise ValueError("Cannot export an empty vector index.")
        if not self._documents:
            raise ValueError("Cannot export an index without documents.")

        faiss = self._faiss()
        buf = faiss.serialize_index(self._index)
        faiss_bytes = bytes(buf)
        index_meta_str = json.dumps(self._metadata, ensure_ascii=False)
        doc_meta_str = json.dumps(self._documents, ensure_ascii=False)
        return faiss_bytes, index_meta_str, doc_meta_str

    def export_zip_bytes(self) -> bytes:
        """Export the index bundle as a compressed ZIP archive in memory."""
        import io
        import zipfile

        faiss_bytes, index_meta_str, doc_meta_str = self.export_bundle_bytes()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("semantic_index.faiss", faiss_bytes)
            zf.writestr("index_metadata.json", index_meta_str)
            zf.writestr("document_metadata.json", doc_meta_str)
        return buffer.getvalue()

    def load_from_zip_bytes(
        self, zip_bytes: bytes, expected_revision_id: str | None = None
    ) -> dict[str, Any]:
        """Restore FAISS index and ordered documents from Backend ZIP archive.

        Validates archive safety, JSON syntax, vector dimensions, document count,
        and revision identity before atomically replacing in-memory state.

        Args:
            zip_bytes: Raw ZIP archive bytes.
            expected_revision_id: Optional revision ID to verify against metadata.

        Returns:
            Parsed index metadata dictionary.

        Raises:
            ValueError: If the archive is unsafe, malformed, or fails validation.
        """
        import io
        import zipfile

        if not zip_bytes:
            raise ValueError("ZIP bytes cannot be empty.")

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                names = zf.namelist()
                for name in names:
                    if ".." in name or name.startswith("/") or name.startswith("\\"):
                        raise ValueError(f"Unsafe ZIP archive entry detected: {name}")

                required_files = {
                    "semantic_index.faiss",
                    "index_metadata.json",
                    "document_metadata.json",
                }
                missing = required_files - set(names)
                if missing:
                    raise ValueError(f"ZIP archive missing required artifact files: {sorted(missing)}")

                faiss_data = zf.read("semantic_index.faiss")
                index_meta_raw = zf.read("index_metadata.json")
                doc_meta_raw = zf.read("document_metadata.json")
        except zipfile.BadZipFile as err:
            raise ValueError(f"Malformed ZIP archive: {err}") from err

        try:
            index_metadata = json.loads(index_meta_raw.decode("utf-8"))
        except Exception as err:
            raise ValueError(f"Invalid index_metadata.json in archive: {err}") from err

        try:
            document_metadata = json.loads(doc_meta_raw.decode("utf-8"))
        except Exception as err:
            raise ValueError(f"Invalid document_metadata.json in archive: {err}") from err

        if not isinstance(index_metadata, dict):
            raise ValueError("index_metadata.json must contain a JSON object.")
        if not isinstance(document_metadata, list):
            raise ValueError("document_metadata.json must contain a JSON array.")

        if expected_revision_id is not None:
            actual_rev = index_metadata.get("revision_id")
            if actual_rev != expected_revision_id:
                raise ValueError(
                    f"Artifact revision mismatch: expected '{expected_revision_id}', got '{actual_rev}'."
                )

        faiss = self._faiss()
        try:
            restored_index = faiss.deserialize_index(np.frombuffer(faiss_data, dtype=np.uint8))
        except Exception as err:
            raise ValueError(f"Failed to deserialize FAISS index from artifact: {err}") from err

        expected_dim = index_metadata.get("embedding_dimension")
        if expected_dim is not None and restored_index.d != expected_dim:
            raise ValueError(
                f"Dimension mismatch: FAISS index d={restored_index.d}, metadata dimension={expected_dim}."
            )

        if restored_index.ntotal != len(document_metadata):
            raise ValueError(
                f"Document count mismatch: FAISS index has {restored_index.ntotal} vectors, "
                f"document_metadata has {len(document_metadata)} entries."
            )

        meta_count = index_metadata.get("document_count")
        if meta_count is not None and meta_count != len(document_metadata):
            raise ValueError(
                f"Metadata document_count ({meta_count}) does not match document_metadata length ({len(document_metadata)})."
            )

        # Atomic replacement into active state only after all validations succeed
        self._index = restored_index
        self._documents = list(document_metadata)
        self._metadata = dict(index_metadata)
        return index_metadata

    def validate_metadata(self, expected: dict[str, Any]) -> None:
        if self._index is None:
            self.load()
        for key, value in expected.items():
            if self._metadata.get(key) != value:
                raise ValueError(f"Semantic index metadata mismatch for '{key}'; rebuild it.")

    def _metadata_path(self) -> Path:
        assert self._artifact_path is not None
        return self._artifact_path.with_suffix(self._artifact_path.suffix + ".metadata.json")
