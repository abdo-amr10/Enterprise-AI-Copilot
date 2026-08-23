"""Configurable offline Sentence Transformers embedding adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np


class EmbeddingService:
    """Load one local model and emit normalized float32 embeddings."""

    def __init__(self, model_path: str | Path, *, model_name: str | None = None,
                 device: str | None = None, batch_size: int = 32,
                 normalize: bool = True) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive.")
        self._model_path = str(model_path)
        self._model_name = model_name or self._model_path
        self._device, self._batch_size, self._normalize = device, batch_size, normalize
        self._model: Any | None = None
        self._embedding_dimension: int | None = None
        self._model_version: str | None = None

    @property
    def model_name(self) -> str: return self._model_name

    @property
    def model_version(self) -> str | None:
        self._load_model()
        return self._model_version

    @property
    def embedding_dimension(self) -> int:
        self._load_model()
        assert self._embedding_dimension is not None
        return self._embedding_dimension

    @property
    def backend(self) -> str: return "sentence-transformers-local"

    @property
    def device(self) -> str: return self._device or "auto"

    def encode_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._encode(texts)

    def encode_query(self, text: str) -> np.ndarray:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Query text must be non-empty.")
        return self._encode([text])[0]

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Compatibility alias retained for local development retrieval."""
        return self.encode_documents(texts)

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        values = list(texts)
        if not values:
            return np.empty((0, self.embedding_dimension), dtype=np.float32)
        if any(not isinstance(text, str) for text in values):
            raise ValueError("Embedding inputs must be strings.")
        model = self._load_model()
        vectors = np.asarray(model.encode(values, batch_size=self._batch_size,
            show_progress_bar=False, normalize_embeddings=self._normalize), dtype=np.float32)
        if vectors.ndim != 2:
            raise ValueError("Embedding model must return a 2-D matrix.")
        if self._normalize:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            if np.any(norms == 0):
                raise ValueError("Embedding model returned a zero vector.")
            vectors = vectors / norms
        return vectors.astype(np.float32, copy=False)

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise RuntimeError("sentence-transformers is required for embedding generation.") from error
            kwargs: dict[str, Any] = {"local_files_only": True}
            if self._device:
                kwargs["device"] = self._device
            self._model = SentenceTransformer(self._model_path, **kwargs)
            get_dimension = getattr(self._model, "get_embedding_dimension", None)
            if not callable(get_dimension):
                # Keeps lightweight test doubles compatible while production
                # uses the Sentence Transformers 6 API above.
                get_dimension = self._model.get_sentence_embedding_dimension
            self._embedding_dimension = int(get_dimension())
            self._model_version = self._read_model_version()
        return self._model

    def _read_model_version(self) -> str | None:
        """Read the packaged Sentence Transformers version when available."""

        config_path = Path(self._model_path) / "config_sentence_transformers.json"
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        version = config.get("__version__", {}).get("sentence_transformers")
        return version if isinstance(version, str) and version.strip() else None
