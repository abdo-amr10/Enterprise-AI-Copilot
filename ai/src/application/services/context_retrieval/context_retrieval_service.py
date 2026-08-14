"""Application use case for query-time semantic context retrieval."""
from typing import Any

from src.application.ports.semantic_repository import SemanticRepository


class ContextRetrievalService:
    """Application service for query-time semantic context retrieval."""

    def __init__(self, semantic_repository: SemanticRepository, default_top_k: int = 8) -> None:
        self._semantic_repository = semantic_repository
        self._default_top_k = default_top_k

    def retrieve(self, question: str, top_k: int | None = None) -> list[dict[str, Any]]:
        limit = top_k if top_k is not None else self._default_top_k
        return self._semantic_repository.retrieve(question, limit)

    def build_llm_context(self, question: str, top_k: int | None = None) -> str:
        results = self.retrieve(question, top_k)
        lines = [
            "SEMANTIC CONTEXT",
            "Use only the supplied semantic metadata.",
            "Do not invent tables, columns, joins, measures, or business rules.",
            "",
        ]

        for result in results:
            lines.append(f"[{result['type']}]")
            lines.append(result["text"])
            lines.append("")

        return "\n".join(lines)
