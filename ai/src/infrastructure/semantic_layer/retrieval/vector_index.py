"""Storage-neutral vector-index contract for semantic retrieval artifacts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence


class VectorIndex(ABC):
    """Derived-index abstraction; it never owns Semantic Layer persistence."""

    @abstractmethod
    def build(
        self,
        documents: Sequence[dict[str, Any]],
        embeddings: Any,
        metadata: dict[str, Any],
    ) -> None: ...

    @abstractmethod
    def search(self, query_embedding: Any, top_k: int) -> list[dict[str, Any]]: ...

    @abstractmethod
    def save(self) -> None: ...

    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def validate_metadata(self, expected: dict[str, Any]) -> None: ...
