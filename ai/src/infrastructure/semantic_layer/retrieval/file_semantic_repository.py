"""Query-time retrieval over the approved semantic layer."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.infrastructure.semantic_layer.retrieval.embedding_service import EmbeddingService
from src.infrastructure.semantic_layer.retrieval.vector_store import LocalVectorStore


class FileSemanticRepository:
    """Read approved semantic metadata and retrieve relevant semantic documents."""

    _SECTIONS = (
        ("entity", "entities"),
        ("relationship", "relationships"),
        ("measure", "measures"),
        ("dimension", "dimensions"),
        ("business_rule", "business_rules"),
    )

    def __init__(self, semantic_layer_path: str | Path, embedding_service: EmbeddingService | None = None, vector_store: LocalVectorStore | None = None) -> None:
        self._semantic_layer_path = Path(semantic_layer_path)
        self._embedding_service = embedding_service
        self._vector_store = vector_store

    def load(self) -> dict[str, Any]:
        with self._semantic_layer_path.open(encoding="utf-8") as file:
            return json.load(file)

    def retrieve(self, question: str, top_k: int = 8) -> list[dict[str, Any]]:
        if self._embedding_service is not None and self._vector_store is not None:
            return self._vector_retrieve(question, top_k)
        return self._keyword_retrieve(question, top_k)

    def _vector_retrieve(self, question: str, top_k: int) -> list[dict[str, Any]]:
        query = self._embedding_service.encode([question])[0]
        return self._vector_store.search(query, top_k)

    def _keyword_retrieve(self, question: str, top_k: int) -> list[dict[str, Any]]:
        documents = self._documents()
        terms = [term for term in question.lower().replace("?", "").split() if term]
        scored = []
        for document in documents:
            text = document["text"].lower()
            score = sum(term in text for term in terms)
            if score:
                scored.append({**document, "score": float(score)})
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:top_k]

    def _documents(self) -> list[dict[str, Any]]:
        layer = self.load()
        documents = []
        for doc_type, section in self._SECTIONS:
            for index, item in enumerate(layer.get(section, [])):
                documents.append({
                    "id": f"{doc_type}:{index}",
                    "type": doc_type,
                    "text": json.dumps(item, ensure_ascii=False),
                    "payload": item,
                })
        return documents
