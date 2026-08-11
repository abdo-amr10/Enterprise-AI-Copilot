"""Persisted semantic-layer repository with optional local vector retrieval."""
import json
from pathlib import Path
from typing import Any

from ai.src.infrastructure.semantic_layer.retrieval.embedding_service import EmbeddingService
from ai.src.infrastructure.semantic_layer.retrieval.vector_store import LocalVectorStore


class FileSemanticRepository:
    """Reads only the activated semantic layer at query time."""

    _GROUPS = {
        "entities": "entities",
        "relationships": "relationships",
        "measures": "measures",
        "dimensions": "dimensions",
        "business_rules": "rules",
    }

    def __init__(
        self,
        semantic_root: str | Path,
        embedding_service: EmbeddingService | None = None,
        vector_store: LocalVectorStore | None = None,
    ) -> None:
        self._semantic_root = Path(semantic_root)
        self._embedding_service = embedding_service
        self._vector_store = vector_store

    def load(self) -> dict[str, Any]:
        return {
            group: self._read(f"{group}/{filename}.json")
            for group, filename in (
                ("entities", "entities"),
                ("relationships", "relationships"),
                ("measures", "measures"),
                ("dimensions", "dimensions"),
                ("business_rules", "business_rules"),
                ("metadata", "metadata"),
            )
        }

    def retrieve(self, question: str, top_k: int) -> list[dict[str, Any]]:
        documents = self._documents()

        if self._embedding_service is not None and self._vector_store is not None:
            query_embedding = self._embedding_service.encode([question])[0]
            return self._vector_store.search(query_embedding, top_k)

        return self._keyword_retrieve(question, documents, top_k)

    def _documents(self) -> list[dict[str, Any]]:
        layer = self.load()
        documents: list[dict[str, Any]] = []

        for group, key in self._GROUPS.items():
            for index, item in enumerate(layer[group].get(key, [])):
                documents.append(
                    {
                        "id": f"{group}:{index}",
                        "type": group,
                        "text": json.dumps(item, ensure_ascii=False),
                        "payload": item,
                    }
                )

        return documents

    @staticmethod
    def _keyword_retrieve(
        question: str,
        documents: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        terms = question.lower().split()
        scored = []

        for document in documents:
            text = document["text"].lower()
            score = sum(term in text for term in terms)

            if score:
                scored.append({**document, "score": score})

        return sorted(
            scored,
            key=lambda document: document["score"],
            reverse=True,
        )[:top_k]

    def _read(self, relative_path: str) -> dict[str, Any]:
        with (self._semantic_root / relative_path).open(encoding="utf-8") as file:
            return json.load(file)
