"""Embedding provider interface and local SentenceTransformer implementation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol, Sequence, runtime_checkable

import numpy as np

logger = logging.getLogger(__name__)


@runtime_checkable
class IntentEmbeddingProvider(Protocol):
    """Protocol for generating normalized text embeddings for intent routing."""

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Encode multiple texts into a 2D float32 normalized matrix."""
        ...

    def encode_single(self, text: str) -> np.ndarray:
        """Encode a single text into a 1D float32 normalized vector."""
        ...

    @property
    def embedding_dimension(self) -> int:
        """Return the embedding dimension size."""
        ...


_MODEL_CACHE: dict[tuple[str, str | None], tuple[Any, int]] = {}


class LocalMiniLMEmbeddingProvider:
    """Local, offline SentenceTransformer embedding provider for all-MiniLM-L6-v2."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        device: str | None = None,
        batch_size: int = 32,
    ) -> None:
        self._model_path = Path(model_path)
        self._device = device
        self._batch_size = max(1, batch_size)
        self._model: Any | None = None
        self._embedding_dimension: int | None = None

    def _ensure_loaded(self) -> Any:
        if self._model is not None:
            return self._model

        cache_key = (str(self._model_path.resolve()), self._device)
        if cache_key in _MODEL_CACHE:
            self._model, self._embedding_dimension = _MODEL_CACHE[cache_key]
            return self._model

        if not self._model_path.exists():
            raise FileNotFoundError(
                f"Local embedding model not found at: {self._model_path}"
            )
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for local embedding generation."
            ) from exc

        kwargs: dict[str, Any] = {"local_files_only": True}
        if self._device:
            kwargs["device"] = self._device

        logger.info("Loading local semantic routing model from: %s", self._model_path)
        self._model = SentenceTransformer(str(self._model_path), **kwargs)

        get_dim = getattr(self._model, "get_embedding_dimension", None)
        if not callable(get_dim):
            get_dim = getattr(self._model, "get_sentence_embedding_dimension", None)
        self._embedding_dimension = int(get_dim()) if callable(get_dim) else 384
        _MODEL_CACHE[cache_key] = (self._model, self._embedding_dimension)
        logger.info(
            "Local semantic routing model loaded successfully (dim=%d).",
            self._embedding_dimension,
        )
        return self._model

    @property
    def embedding_dimension(self) -> int:
        self._ensure_loaded()
        assert self._embedding_dimension is not None
        return self._embedding_dimension

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        values = list(texts)
        if not values:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)

        model = self._ensure_loaded()
        vectors = np.asarray(
            model.encode(
                values,
                batch_size=self._batch_size,
                show_progress_bar=False,
                normalize_embeddings=True,
            ),
            dtype=np.float32,
        )
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)

        # Ensure unit normalization for safe cosine similarity via dot product
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return (vectors / norms).astype(np.float32, copy=False)

    def encode_single(self, text: str) -> np.ndarray:
        clean = (text or "").strip()
        if not clean:
            return np.zeros((self.embedding_dimension,), dtype=np.float32)
        matrix = self.encode([clean])
        return matrix[0]
