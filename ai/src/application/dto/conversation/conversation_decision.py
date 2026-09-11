"""The Conversation Layer's structured decision output (spec section 16)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ConversationDecision:
    classification: str
    confidence: float
    next_action: str
    context_requirement: str = "NONE"
    retrieved_turn_ids: tuple[str, ...] = field(default_factory=tuple)
    resolved_question: Optional[str] = None
    direct_answer: Optional[str] = None
    clarification_message: Optional[str] = None
    scope_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "classification": self.classification,
            "confidence": self.confidence,
            "context_requirement": self.context_requirement,
            "retrieved_turn_ids": list(self.retrieved_turn_ids),
            "resolved_question": self.resolved_question,
            "next_action": self.next_action,
        }
