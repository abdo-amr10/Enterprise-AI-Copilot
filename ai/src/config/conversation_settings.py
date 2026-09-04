"""Runtime configuration for the Conversation Layer.

Configuration is intentionally kept outside application business logic,
matching the existing SelfCorrectionSettings / SemanticSettings pattern.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationSettings:
    # Number of most-recent turns considered as CANDIDATE context for the
    # current question. This is a ceiling, not what gets sent to the LLM --
    # the Follow-up Analyzer and Context Retriever still only pull the
    # specific fields actually required (see context_retriever.py).
    context_window: int = 5
