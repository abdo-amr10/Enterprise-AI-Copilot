"""Structured semantic follow-up detector with specialist entity normalization."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional

from src.application.services.conversation.extraction.entity_recognizer import (
    EntityRecognizer,
    get_entity_recognizer,
)
from src.application.services.conversation.followup.legacy_fallback import (
    LegacyFollowupFallbackDetector,
)
from src.application.services.conversation.followup.models import (
    FollowupConfidence,
    FollowupDetectionResult,
    FollowupType,
)
from src.application.services.conversation.normalization.normalizer import RequestNormalizer
from src.application.services.conversation.state.conversation_state import ConversationState

if TYPE_CHECKING:
    from src.application.services.conversation.semantic_routing.application.semantic_turn_parser import (
        SemanticTurnParser,
    )

logger = logging.getLogger(__name__)


class FollowupDetector:
    """
    Classifies follow-up operations using structured semantic parsing and specialist entity recognition.

    In production, this detector delegates semantic classification to `SemanticTurnParser`
    and dynamic entity extraction to `EntityRecognizer` (Microsoft Recognizers-Text).
    For backwards compatibility with offline unit tests that execute without a local LLM,
    it delegates unhandled utterances to the isolated `LegacyFollowupFallbackDetector`.
    """

    def __init__(
        self,
        semantic_parser: Optional[SemanticTurnParser] = None,
        entity_recognizer: Optional[EntityRecognizer] = None,
        enable_legacy_fallback: bool = True,
    ) -> None:
        self._entity_recognizer = entity_recognizer or get_entity_recognizer()
        self._semantic_parser = semantic_parser
        self._enable_legacy_fallback = enable_legacy_fallback
        self._legacy_fallback: Optional[LegacyFollowupFallbackDetector] = (
            LegacyFollowupFallbackDetector(entity_recognizer=self._entity_recognizer)
            if enable_legacy_fallback
            else None
        )

    def _is_temporal_expression(self, text: str) -> bool:
        """Determine whether text represents a temporal/date/time expression dynamically using EntityRecognizer."""
        if not text or not text.strip():
            return False
        clean = text.strip().lower()
        if re.match(r"^\d{4}$", clean):
            return True
        results = self._entity_recognizer.extract_datetime(clean)
        if results:
            words = clean.split()
            if len(words) <= 3:
                return True
            r = results[0]
            if len(r.text.strip()) >= len(clean) * 0.7:
                return True
        return False

    def _extract_limit_value(self, raw_match_val: Optional[str], full_query: str) -> str:
        """Extract clean limit digit string from raw match or query using EntityRecognizer."""
        if raw_match_val and raw_match_val.isdigit():
            return raw_match_val
        if raw_match_val:
            num = self._entity_recognizer.extract_limit(raw_match_val, default=0)
            if num > 0:
                return str(num)
        num = self._entity_recognizer.extract_limit(full_query, default=5)
        return str(num)

    def detect(
        self,
        question: str,
        state: Optional[ConversationState] = None,
        has_history: bool = False,
    ) -> FollowupDetectionResult:
        """
        Detect follow-up operations.

        First attempts structured semantic parsing via `SemanticTurnParser`. If unavailable
        or inconclusive (e.g. offline unit testing), delegates to `LegacyFollowupFallbackDetector`.
        """
        norm_q = RequestNormalizer.normalize(question)

        # Context awareness check
        has_context = has_history or (state is not None and (
            state.active_query_state is not None or state.last_successful_execution is not None
        ))

        # ---------------------------------------------------------------------
        # 1. Primary Semantic Path via SemanticTurnParser (Production Runtime)
        # ---------------------------------------------------------------------
        if self._semantic_parser is not None and has_context:
            try:
                turn_intent = self._semantic_parser.parse_turn(question, has_history=has_history)
                if turn_intent.action == "RESET":
                    return FollowupDetectionResult(
                        confidence_level=FollowupConfidence.INDEPENDENT,
                        confidence_score=turn_intent.confidence_score,
                        reason="Explicit context reset requested.",
                        is_context_reset=True,
                        clean_question=turn_intent.target_entity,
                    )
                if turn_intent.action == "MODIFY_QUERY" and turn_intent.confidence_score >= 0.8:
                    if turn_intent.limit is not None and turn_intent.limit > 0:
                        return FollowupDetectionResult(
                            confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                            operation_type=FollowupType.LIMIT_CHANGE,
                            target_value=str(turn_intent.limit),
                            confidence_score=turn_intent.confidence_score,
                        )
                    if turn_intent.time is not None:
                        target = turn_intent.time.source_text or turn_intent.time.start or ""
                        return FollowupDetectionResult(
                            confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                            operation_type=FollowupType.TIME_CHANGE,
                            target_value=target,
                            confidence_score=turn_intent.confidence_score,
                        )
                    if turn_intent.sort is not None:
                        sort_target = f"{turn_intent.sort.target} {turn_intent.sort.direction}".strip()
                        return FollowupDetectionResult(
                            confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                            operation_type=FollowupType.SORT_CHANGE,
                            target_value=sort_target,
                            confidence_score=turn_intent.confidence_score,
                        )
                    if turn_intent.group_by:
                        return FollowupDetectionResult(
                            confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                            operation_type=FollowupType.GROUP_BY_CHANGE,
                            target_value=turn_intent.group_by,
                            confidence_score=turn_intent.confidence_score,
                        )
                    if turn_intent.filters:
                        val = turn_intent.filters[0].value or turn_intent.filters[0].target
                        return FollowupDetectionResult(
                            confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                            operation_type=FollowupType.FILTER_CHANGE,
                            target_value=str(val),
                            confidence_score=turn_intent.confidence_score,
                        )
            except Exception as exc:
                logger.warning("SemanticTurnParser primary path failed in FollowupDetector: %s", exc)

        # ---------------------------------------------------------------------
        # 2. Quarantined Fallback Path (Offline Unit Tests & Graceful Fallback)
        # ---------------------------------------------------------------------
        if self._legacy_fallback is not None:
            return self._legacy_fallback.detect_fallback(
                norm_q=norm_q,
                has_context=has_context,
            )

        # ---------------------------------------------------------------------
        # 3. Default (When fallback is disabled and no semantic follow-up detected)
        # ---------------------------------------------------------------------
        return FollowupDetectionResult(
            confidence_level=FollowupConfidence.INDEPENDENT,
            confidence_score=1.0,
            reason="No active conversation context." if not has_context else "Query does not contain continuation markers.",
        )
