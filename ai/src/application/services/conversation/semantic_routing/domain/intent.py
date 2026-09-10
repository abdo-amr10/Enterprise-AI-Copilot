"""Canonical conversation intent enumeration for semantic routing."""

from __future__ import annotations

from enum import Enum


class ConversationIntent(str, Enum):
    """Semantic intent classification of a user conversation turn."""

    NEW_DATABASE_QUERY = "NEW_DATABASE_QUERY"
    CAPABILITY = "CAPABILITY"
    LIMIT_CHANGE = "LIMIT_CHANGE"
    SORT_CHANGE = "SORT_CHANGE"
    GROUP_BY_CHANGE = "GROUP_BY_CHANGE"
    FILTER_CHANGE = "FILTER_CHANGE"
    CORRECTION = "CORRECTION"
    PRONOUN_REFERENCE = "PRONOUN_REFERENCE"
    RESET_CONTEXT = "RESET_CONTEXT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    AMBIGUOUS = "AMBIGUOUS"

    @property
    def is_followup(self) -> bool:
        return self in (
            ConversationIntent.LIMIT_CHANGE,
            ConversationIntent.SORT_CHANGE,
            ConversationIntent.GROUP_BY_CHANGE,
            ConversationIntent.FILTER_CHANGE,
            ConversationIntent.CORRECTION,
            ConversationIntent.PRONOUN_REFERENCE,
        )
