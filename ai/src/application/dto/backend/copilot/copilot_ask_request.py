"""AI-runtime input for the Backend's public copilot ask endpoint."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CopilotAskRequest:
    question: str
    conversation: tuple[dict[str, Any], ...] = ()
    correlation_id: str | None = None
    traceparent: str | None = None

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("question cannot be empty.")
        if not isinstance(self.conversation, tuple):
            raise ValueError("conversation must be a tuple.")

    @property
    def user_question(self) -> str:
        """Alias for question matching conversation layer naming conventions."""
        return self.question
