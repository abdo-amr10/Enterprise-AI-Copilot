"""The Conversation Turn model, and the adapter that reads it out of the
existing, unchanged ``CopilotAskRequest.conversation`` field.

Backend already sends ``conversation: tuple[dict[str, Any], ...]`` on every
``/internal/copilot/ask`` call (see copilot_ask_request.py) and one
convention already lives inside that free-form shape: system messages
whose content starts with ``"RLS_CORRECTION:"`` (see
copilot_runtime_pipeline.py). This module adds a second convention,
``{"role": "turn", ...}``, instead of introducing a new field or DTO --
so no existing contract changes, and any Backend that never sends
``role: "turn"`` entries gets IDENTICAL behavior to today (zero turns
found -> the Conversation Layer always resolves to INDEPENDENT).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ConversationTurn:
    turn_id: str
    user_question: str
    resolved_question: Optional[str] = None
    generated_sql: Optional[str] = None
    # A short natural-language summary, not raw rows -- this is exactly the
    # `textSummary` the AI runtime already produces via
    # PostQueryResponseSummarizer/`/internal/copilot/format-execution-result`.
    # Backend is expected to store and re-send that same string; the
    # Conversation Layer does not re-derive it from raw execution rows.
    execution_result_summary: Optional[str] = None
    execution_status: Optional[str] = None
    classification: Optional[str] = None
    timestamp: Optional[str] = None

    @staticmethod
    def from_raw(raw: dict[str, Any]) -> Optional["ConversationTurn"]:
        """Parses one `{"role": "turn", ...}` dict. Returns None if malformed."""
        if raw.get("role") != "turn":
            return None
        turn_id = raw.get("turn_id")
        user_question = raw.get("user_question")
        if not turn_id or not user_question:
            return None
        return ConversationTurn(
            turn_id=str(turn_id),
            user_question=str(user_question),
            resolved_question=raw.get("resolved_question"),
            generated_sql=raw.get("generated_sql"),
            execution_result_summary=raw.get("execution_result_summary"),
            execution_status=raw.get("execution_status"),
            classification=raw.get("classification"),
            timestamp=raw.get("timestamp"),
        )

    def field(self, name: str) -> Any:
        return getattr(self, name, None)
