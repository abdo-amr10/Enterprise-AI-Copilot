"""Conversation Manager.

Responsibility (per spec section 4): identify the conversation's turns
from what Backend already sends, and apply the context window. It does
NOT classify, resolve, or touch SQL generation logic -- that's the
Follow-up Analyzer / Context Resolver / NL2SQL pipeline's job.

This is the ONLY place that reads the raw `conversation` tuple's shape,
so if that wire format ever needs to change, this is the one file that
changes.
"""

from __future__ import annotations

from typing import Any

from src.application.services.conversation.models import ConversationTurn
from src.config.conversation_settings import ConversationSettings


class ConversationManager:
    def __init__(self, settings: ConversationSettings | None = None) -> None:
        self._settings = settings or ConversationSettings()

    def load_recent_turns(
        self, raw_conversation: tuple[dict[str, Any], ...]
    ) -> tuple[ConversationTurn, ...]:
        """Extracts turns from the raw conversation payload and returns the
        most recent `context_window` of them, oldest first.

        Non-turn entries (e.g. the existing RLS_CORRECTION system messages)
        are silently ignored here -- they are handled separately by
        CopilotRuntimePipeline, unchanged.
        """
        turns = [
            turn
            for raw in raw_conversation
            if (turn := ConversationTurn.from_raw(raw)) is not None
        ]
        if self._settings.context_window <= 0:
            return ()
        return tuple(turns[-self._settings.context_window:])

    @staticmethod
    def latest_turn(turns: tuple[ConversationTurn, ...]) -> ConversationTurn | None:
        return turns[-1] if turns else None
