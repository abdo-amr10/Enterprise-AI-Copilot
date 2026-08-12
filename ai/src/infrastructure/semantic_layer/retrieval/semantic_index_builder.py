"""Build a vector index from the approved semantic layer."""
from __future__ import annotations

from typing import Any

from src.infrastructure.semantic_layer.retrieval.embedding_service import EmbeddingService
from src.infrastructure.semantic_layer.retrieval.vector_store import LocalVectorStore


class SemanticIndexBuilder:
    def __init__(self, embedding_service: EmbeddingService, vector_store: LocalVectorStore) -> None:
        self._embedding_service = embedding_service
        self._vector_store = vector_store

    def build(self, layer: dict[str, Any]) -> dict[str, Any]:
        documents = self._documents(layer)
        embeddings = self._embedding_service.encode([document["text"] for document in documents])
        self._vector_store.build(documents, embeddings)
        return {
            "document_count": len(documents),
            "embedding_dimension": int(embeddings.shape[1]) if len(embeddings) else 0,
            "embedding_backend": self._embedding_service.backend,
        }

    @staticmethod
    def _documents(layer: dict[str, Any]) -> list[dict[str, Any]]:
        sections = (
            ("entity", "entities"),
            ("relationship", "relationships"),
            ("measure", "measures"),
            ("dimension", "dimensions"),
            ("business_rule", "business_rules"),
        )
        documents = []
        for doc_type, section in sections:
            for index, item in enumerate(layer.get(section, [])):
                documents.append({
                    "id": f"{doc_type}:{index}",
                    "type": doc_type,
                    "text": SemanticIndexBuilder._render(doc_type, item),
                    "payload": item,
                })
        return documents

    @staticmethod
    def _render(doc_type: str, item: dict[str, Any]) -> str:
        fields = [f"type: {doc_type}"]
        for key, value in item.items():
            if key == "source":
                continue
            if isinstance(value, (dict, list)):
                value = str(value)
            fields.append(f"{key}: {value}")
        return " | ".join(fields)
