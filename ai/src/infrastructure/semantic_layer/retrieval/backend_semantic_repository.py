"""Retrieval adapter whose authoritative semantic state is the Backend."""

from __future__ import annotations

from typing import Any

from src.infrastructure.backend.backend_semantic_client import BackendSemanticClient
from src.infrastructure.semantic_layer.retrieval.semantic_document_builder import SemanticDocumentBuilder


class BackendSemanticRepository:
    """Fetches the currently approved revision for each retrieval request.

    No local semantic file is used as a fallback. A future vector index may be
    added as a versioned cache, but this adapter keeps Backend state authoritative.
    """

    def __init__(self, client: BackendSemanticClient | None = None) -> None:
        self._client = client or BackendSemanticClient()

    def load(self) -> dict[str, Any]:
        status = self._client.get_status()
        if status.get("status") != "Approved":
            raise ValueError("Runtime retrieval requires a Backend-approved semantic revision.")
        revision_id = status.get("revisionId")
        if not isinstance(revision_id, str) or not revision_id:
            raise ValueError("Backend semantic status did not provide revisionId.")
        layer = self._client.load_revision(revision_id)
        metadata = layer.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("Approved Backend semantic revision has no metadata.")
        return layer

    def retrieve(self, question: str, top_k: int = 8) -> list[dict[str, Any]]:
        terms = [term for term in question.lower().replace("?", "").split() if term]
        scored: list[dict[str, Any]] = []
        for document in SemanticDocumentBuilder().build(self.load()):
            score = sum(term in document["text"].lower() for term in terms)
            if score:
                scored.append({**document, "type": document["object_type"], "score": float(score)})
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:top_k]
