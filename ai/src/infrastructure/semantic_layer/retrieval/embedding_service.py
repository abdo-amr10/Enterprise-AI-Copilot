"""Embedding adapter with an optional SentenceTransformers backend and deterministic fallback."""
from __future__ import annotations

import hashlib
from typing import Sequence

import numpy as np


class EmbeddingService:
    """Create normalized vectors for semantic documents."""

    def __init__(self, model_name: str, fallback_dimension: int = 384) -> None:
        self._model_name = model_name
        self._model = None
        self.dimension = fallback_dimension
        self.backend = "uninitialized"

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
                self.dimension = int(self._model.get_sentence_embedding_dimension())
                self.backend = "sentence-transformers"
            except ImportError:
                self.backend = "deterministic-fallback"
        return self._model

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        model = self._get_model()
        if model is not None:
            return np.asarray(model.encode(list(texts), normalize_embeddings=True), dtype="float32")
        return np.vstack([self._fallback(text) for text in texts]).astype("float32")

    def _fallback(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimension, dtype="float32")
        tokens = [token for token in text.lower().replace("_", " ").replace(".", " ").split() if token]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector
