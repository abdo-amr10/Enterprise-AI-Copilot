"""Internal request contract for semantic-context retrieval."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SemanticRetrievalRequest:
    question: str
    conversation: tuple[dict[str, Any], ...]
    top_k: int | None = None

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("question cannot be empty.")
        if not isinstance(self.conversation, tuple):
            raise ValueError("conversation must be a tuple.")
        if self.top_k is not None and self.top_k <= 0:
            raise ValueError("top_k must be greater than zero.")
