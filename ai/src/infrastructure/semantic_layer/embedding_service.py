"""Infrastructure adapter for the local embedding model."""
from typing import Sequence


class EmbeddingService:
    """Creates embeddings for semantic documents.

    Embeddings are built/updated when the semantic layer changes.
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def encode(self, texts: Sequence[str]):
        return self._get_model().encode(
            list(texts),
            normalize_embeddings=True,
        )
