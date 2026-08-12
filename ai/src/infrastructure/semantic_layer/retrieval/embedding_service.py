"""Local embedding adapter using SentenceTransformers."""
from __future__ import annotations

from typing import Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

class EmbeddingService:
    """Create normalized vectors using a local embedding model."""

    def __init__(self, model_path: str) -> None:
        self._model_path = model_path
        self._model = None
        self.dimension = 0
        self.backend = "uninitialized"

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(
                self._model_path,
                local_files_only=True,
            )

            self.dimension = int(
                self._model.get_embedding_dimension()
            )

            self.backend = "sentence-transformers-local"

        return self._model

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        model = self._get_model()

        return np.asarray(
            model.encode(
                list(texts),
                normalize_embeddings=True,
            ),
            dtype="float32",
        )