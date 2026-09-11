"""Domain models for semantic intent routing."""

from src.application.services.conversation.semantic_routing.domain.intent import (
    ConversationIntent,
)
from src.application.services.conversation.semantic_routing.domain.classification_result import (
    IntentClassificationResult,
)

__all__ = ["ConversationIntent", "IntentClassificationResult"]
