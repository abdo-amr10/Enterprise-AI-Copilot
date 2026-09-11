"""Abstract repository contracts defining boundaries for state, replay, and results."""

from __future__ import annotations

from typing import Optional, Protocol

from src.application.services.conversation.replay.replay_cache import ReplayEntry
from src.application.services.conversation.state.conversation_state import (
    ConversationState,
    ResultMetadata,
)


class ConversationStateRepository(Protocol):
    """Abstraction for loading and persisting conversation state.

    The Backend is the persistent system of record. AI Runtime uses this interface
    to interact with the persistence boundary.
    """
    def get(self, conversation_id: str) -> Optional[ConversationState]:
        ...

    def save(self, state: ConversationState) -> None:
        ...

    def delete(self, conversation_id: str) -> None:
        ...


class ConversationReplayRepository(Protocol):
    """Abstraction for exact replay caching."""
    def get(self, fingerprint: str) -> Optional[ReplayEntry]:
        ...

    def save(self, entry: ReplayEntry) -> None:
        ...

    def invalidate_by_revision(self, semantic_revision_id: str) -> int:
        ...


class ConversationResultRepository(Protocol):
    """Abstraction for accessing executed query result data."""
    def get_result(self, execution_id: str) -> Optional[ResultMetadata]:
        ...
