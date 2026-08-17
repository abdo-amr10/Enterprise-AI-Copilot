"""Build a vector index from an approved Semantic Layer."""

from __future__ import annotations

from typing import Any

from src.infrastructure.semantic_layer.retrieval.embedding_service import (
    EmbeddingService,
)
from src.infrastructure.semantic_layer.retrieval.vector_store import (
    LocalVectorStore,
)


class SemanticIndexBuilder:
    """Create embeddings and build the local semantic vector index."""

    _SECTIONS = (
        ("entity", "entities"),
        ("relationship", "relationships"),
        ("measure", "measures"),
        ("dimension", "dimensions"),
        ("business_rule", "business_rules"),
    )

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: LocalVectorStore,
    ) -> None:
        self._embedding_service = embedding_service
        self._vector_store = vector_store

    def build(
        self,
        layer: dict[str, Any],
    ) -> dict[str, Any]:
        """Build an index for one approved Semantic Layer revision."""

        metadata = layer.get("metadata", {})

        semantic_layer_id = metadata.get("semantic_layer_id")
        revision_id = metadata.get("revision_id")

        if not semantic_layer_id:
            raise ValueError(
                "semantic_layer_id is required."
            )

        if not revision_id:
            raise ValueError(
                "revision_id is required."
            )

        documents = self._documents(
            layer=layer,
            semantic_layer_id=semantic_layer_id,
            revision_id=revision_id,
        )

        embeddings = self._embedding_service.encode(
            [document["text"] for document in documents]
        )

        self._vector_store.build(
            documents,
            embeddings,
            metadata={
                "index_version": 1,
                "semantic_layer_id": semantic_layer_id,
                "revision_id": revision_id,
                "document_count": len(documents),
                "embedding_dimension": int(embeddings.shape[1]) if len(embeddings) else 0,
                "embedding_backend": self._embedding_service.backend,
            },
        )

        return {
            "semantic_layer_id": semantic_layer_id,
            "revision_id": revision_id,
            "document_count": len(documents),
            "embedding_dimension": (
                int(embeddings.shape[1])
                if len(embeddings)
                else 0
            ),
            "embedding_backend": self._embedding_service.backend,
            "index_version": 1,
        }

    @classmethod
    def _documents(
        cls,
        layer: dict[str, Any],
        semantic_layer_id: str,
        revision_id: str,
    ) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []

        for doc_type, section in cls._SECTIONS:
            for item in layer.get(section, []):
                if not isinstance(item, dict):
                    continue

                documents.append(
                    {
                        "id": cls._document_id(
                            semantic_layer_id,
                            revision_id,
                            doc_type,
                            item,
                        ),
                        "type": doc_type,
                        "text": cls._render(
                            doc_type,
                            item,
                        ),
                        "payload": item,
                        "semanticLayerId": semantic_layer_id,
                        "revisionId": revision_id,
                    }
                )

        return documents

    @staticmethod
    def _document_id(
        semantic_layer_id: str,
        revision_id: str,
        doc_type: str,
        item: dict[str, Any],
    ) -> str:
        name = item.get("name")

        if not name:
            raise ValueError(
                f"Semantic {doc_type} must contain a name."
            )

        return (
            f"{semantic_layer_id}:"
            f"{revision_id}:"
            f"{doc_type}:"
            f"{name}"
        )

    @staticmethod
    def _render(
        doc_type: str,
        item: dict[str, Any],
    ) -> str:
        fields = [f"type: {doc_type}"]

        for key, value in item.items():
            if key == "source":
                continue

            if isinstance(value, (dict, list)):
                value = str(value)

            fields.append(
                f"{key}: {value}"
            )

        return " | ".join(fields)
