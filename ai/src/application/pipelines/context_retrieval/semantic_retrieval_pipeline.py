"""Adapter from the retrieval use case to the internal API contract."""

from __future__ import annotations

from typing import Any

from src.application.dto.backend.copilot.semantic_retrieval_request import (
    SemanticRetrievalRequest,
)
from src.application.dto.backend.copilot.semantic_retrieval_response import (
    SemanticRetrievalResponse,
)
from src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)


class SemanticRetrievalPipeline:
    """Expose the vector-retrieved approved semantic slice to internal callers.

    Relevance is delegated to ``ContextRetrievalService`` and its production
    ``BackendSemanticRepository``; this adapter only projects those selected
    documents onto the existing internal response contract.
    """

    def __init__(self, retrieval_service: ContextRetrievalService) -> None:
        self._retrieval_service = retrieval_service

    def run(self, request: SemanticRetrievalRequest) -> SemanticRetrievalResponse:
        """Retrieve relevant semantic context and project it onto the response contract.

        Args:
            request: The semantic retrieval request containing the question and optional top_k.

        Returns:
            SemanticRetrievalResponse containing sorted relevant tables and unique business rules.
        """
        documents = self._retrieval_service.retrieve(
            question=request.question,
            top_k=request.top_k,
        )
        tables: set[str] = set()
        business_rules: list[str] = []

        for document in documents:
            payload = document.get("payload", {})
            if isinstance(payload, dict):
                self._collect_tables(payload, tables)
            if (document.get("object_type") or document.get("type")) == "business_rule":
                text = payload.get("description") if isinstance(payload, dict) else None
                if isinstance(text, str) and text.strip():
                    business_rules.append(text)

        return SemanticRetrievalResponse(
            status="Success",
            tables=tuple(sorted(tables)),
            business_rules=tuple(dict.fromkeys(business_rules)),
        )

    @classmethod
    def _collect_tables(cls, value: Any, tables: set[str]) -> None:
        """Recursively scan payload dictionary/list structures to collect table names.

        Args:
            value: The data structure or nested payload to inspect.
            tables: Set to collect discovered table names into.
        """
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"table", "source_table", "from_table", "to_table"} and isinstance(item, str):
                    tables.add(item)
                elif key == "mapping" and isinstance(item, str) and item.strip():
                    tables.add(item.split(".", 1)[0].strip())
                else:
                    cls._collect_tables(item, tables)
        elif isinstance(value, list):
            for item in value:
                cls._collect_tables(item, tables)
