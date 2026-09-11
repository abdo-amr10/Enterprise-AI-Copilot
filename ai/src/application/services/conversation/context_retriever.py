"""Context Retriever (spec section 7).

Deliberately dumb and field-scoped: given a turn and the list of fields a
ContextRequirement calls for, return exactly those fields -- never the
whole ConversationTurn object, and never more turns than were passed in.
No LLM call happens here.
"""

from __future__ import annotations

from typing import Any

from src.application.services.conversation.models import ConversationTurn


class ContextRetriever:
    @staticmethod
    def retrieve(turn: ConversationTurn, fields: tuple[str, ...]) -> dict[str, Any]:
        return {name: turn.field(name) for name in fields if turn.field(name) is not None}
