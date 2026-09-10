"""Outcome of semantic intent classification with confidence and margin diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.application.services.conversation.semantic_routing.domain.intent import (
    ConversationIntent,
)


@dataclass(frozen=True)
class IntentClassificationResult:
    """Classified intent with full confidence and margin scoring."""

    intent: ConversationIntent
    confidence_score: float
    margin: float
    is_ambiguous: bool = False
    second_intent: Optional[ConversationIntent] = None
    second_score: float = 0.0
    matched_prototype: Optional[str] = None
    reason: Optional[str] = None
    all_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "confidence_score": self.confidence_score,
            "margin": self.margin,
            "is_ambiguous": self.is_ambiguous,
            "second_intent": self.second_intent.value if self.second_intent else None,
            "second_score": self.second_score,
            "matched_prototype": self.matched_prototype,
            "reason": self.reason,
        }
