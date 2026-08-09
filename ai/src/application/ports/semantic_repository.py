"""Application boundary for persisted semantic-layer access."""
from typing import Any, Protocol


class SemanticRepository(Protocol):
    def retrieve(self, question: str, top_k: int) -> list[dict[str, Any]]:
        """Retrieve semantic context for a user question."""
        ...

    def load(self) -> dict[str, Any]:
        """Load the persisted semantic layer."""
        ...
