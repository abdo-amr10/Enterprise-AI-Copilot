"""Routing decision types and observability contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ConversationRoute(str, Enum):
    EXACT_REPLAY = "EXACT_REPLAY"
    RESULT_ANSWER = "RESULT_ANSWER"
    FOLLOW_UP_QUERY = "FOLLOW_UP_QUERY"
    NEW_DATABASE_QUERY = "NEW_DATABASE_QUERY"
    SEMANTIC_REUSE = "SEMANTIC_REUSE"
    CAPABILITY = "CAPABILITY"
    UNSUPPORTED = "UNSUPPORTED"
    UNRESOLVED_CONTEXT = "UNRESOLVED_CONTEXT"
    EXECUTION_ERROR = "EXECUTION_ERROR"


@dataclass
class RoutingDecision:
    """The authoritative outcome of the Conversation Router cascade."""
    route: ConversationRoute
    is_success: bool
    generated_sql: Optional[str] = None
    text_summary: Optional[str] = None
    presentation_type: str = "DataTable"
    error_message: Optional[str] = None
    resolved_question: Optional[str] = None
    direct_answer: Optional[str] = None

    # Observability metadata
    cache_hit: bool = False
    cache_type: Optional[str] = None
    state_loaded: bool = False
    result_resolution: Optional[str] = None
    followup_detected: bool = False
    followup_confidence: Optional[str] = None
    semantic_lookup_used: bool = False
    semantic_intent: Optional[str] = None
    semantic_confidence: Optional[float] = None
    llm_used_by_conversation_layer: bool = False
    text_to_sql_called: bool = False
    reason_for_fallback: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_observability_dict(self) -> dict[str, Any]:
        return {
            "conversation_route": self.route.value,
            "cache_hit": self.cache_hit,
            "cache_type": self.cache_type,
            "state_loaded": self.state_loaded,
            "result_resolution": self.result_resolution,
            "followup_detected": self.followup_detected,
            "followup_confidence": self.followup_confidence,
            "semantic_lookup_used": self.semantic_lookup_used,
            "semantic_intent": self.semantic_intent,
            "semantic_confidence": self.semantic_confidence,
            "llm_used_by_conversation_layer": self.llm_used_by_conversation_layer,
            "text_to_sql_called": self.text_to_sql_called,
            "reason_for_fallback": self.reason_for_fallback,
        }

