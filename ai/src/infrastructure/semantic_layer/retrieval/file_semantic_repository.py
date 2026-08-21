"""Query-time retrieval over the approved Semantic Layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.infrastructure.semantic_layer.retrieval.embedding_service import (
    EmbeddingService,
)
from src.infrastructure.semantic_layer.retrieval.vector_store import (
    LocalVectorStore,
)
from src.infrastructure.semantic_layer.retrieval.semantic_document_builder import (
    SemanticDocumentBuilder,
)


class FileSemanticRepository:
    """Read approved semantic metadata and retrieve semantic documents."""

    def __init__(
        self,
        semantic_layer_path: str | Path,
        embedding_service: EmbeddingService | None = None,
        vector_store: LocalVectorStore | None = None,
    ) -> None:
        self._semantic_layer_path = Path(
            semantic_layer_path
        )
        self._embedding_service = embedding_service
        self._vector_store = vector_store

    def load(self) -> dict[str, Any]:
        """Load the approved Semantic Layer."""

        with self._semantic_layer_path.open(
            encoding="utf-8"
        ) as file:
            layer = json.load(file)

        if not isinstance(layer, dict):
            raise ValueError("Semantic Layer artifact must be a JSON object.")

        metadata = layer.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("status") != "approved":
            raise ValueError(
                "Runtime retrieval requires a human-approved Semantic Layer."
            )

        return layer

    def retrieve(
        self,
        question: str,
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        """Retrieve the most relevant semantic objects."""

        if (
            self._embedding_service is not None
            and self._vector_store is not None
        ):
            return self._vector_retrieve(
                question,
                top_k,
            )

        return self._keyword_retrieve(
            question,
            top_k,
        )

    def _vector_retrieve(
        self,
        question: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Retrieve semantic objects using vector similarity."""

        layer = self.load()
        metadata = layer["metadata"]
        self._vector_store.validate_metadata({
            "index_version": 1,
            "semantic_layer_id": metadata["semantic_layer_id"],
            "revision_id": metadata["revision_id"],
            "embedding_dimension": self._embedding_service.embedding_dimension,
        })
        query_embedding = self._embedding_service.encode_query(question)

        return self._vector_store.search(
            query_embedding,
            top_k,
        )

    def _keyword_retrieve(
        self,
        question: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Fallback keyword-based retrieval."""

        documents = self._documents()

        terms = [
            term
            for term in question.lower()
            .replace("?", "")
            .split()
            if term
        ]

        scored: list[dict[str, Any]] = []

        for document in documents:
            text = document["text"].lower()

            score = sum(
                term in text
                for term in terms
            )

            if score:
                scored.append(
                    {
                        **document,
                        "score": float(score),
                    }
                )

        return sorted(
            scored,
            key=lambda item: item["score"],
            reverse=True,
        )[:top_k]

    def _documents(self) -> list[dict[str, Any]]:
        layer = self.load()

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

        return [
            {
                **document,
                "type": document["object_type"],
                "semanticLayerId": document["semantic_layer_id"],
                "revisionId": document["revision_id"],
            }
            for document in SemanticDocumentBuilder().build(layer)
        ]
