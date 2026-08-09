"""Local vector-index adapter."""
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np


class LocalVectorStore:
    """Persists and searches semantic document embeddings."""

    def __init__(self, index_path: str | Path) -> None:
        self._index_path = Path(index_path)
        self._vectors: np.ndarray | None = None
        self._documents: list[dict[str, Any]] = []

    def build(self, documents: Sequence[dict[str, Any]], embeddings: Any) -> None:
        self._documents = list(documents)
        self._vectors = np.asarray(embeddings, dtype="float32")
        self.save()

    def save(self) -> None:
        if self._vectors is None:
            raise ValueError("Cannot save an empty vector index.")

        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            self._index_path,
            vectors=self._vectors,
            documents=np.array(
                [json.dumps(doc, ensure_ascii=False) for doc in self._documents],
                dtype=object,
            ),
        )

    def load(self) -> None:
        data = np.load(self._index_path, allow_pickle=True)
        self._vectors = data["vectors"]
        self._documents = [
            json.loads(item) for item in data["documents"].tolist()
        ]

    def search(self, query_embedding: Any, top_k: int) -> list[dict[str, Any]]:
        if self._vectors is None:
            self.load()

        query = np.asarray(query_embedding, dtype="float32")
        if query.ndim == 1:
            query = query[None, :]

        scores = (self._vectors @ query.T).ravel()
        ids = np.argsort(-scores)[:top_k]

        return [
            {**self._documents[int(index)], "score": float(scores[int(index)])}
            for index in ids
        ]
