"""
=============================================================================
DEPRECATED - TEST & OFFLINE FALLBACK ONLY
=============================================================================
This module contains legacy heuristic regexes and rule-based dispatching
retained EXCLUSIVELY for backwards compatibility with legacy offline unit
tests that execute without an active Ollama LLM / SemanticTurnParser.

IN PRODUCTION:
In a live production environment with SemanticTurnParser and local LLM active,
this fallback is completely bypassed by the Primary Semantic Path.

TO DELETE IN THE FUTURE:
When legacy unit tests are retired or migrated to semantic assertions,
this file can be safely deleted in its entirety, and the fallback reference
in `FollowupDetector` can be removed or disabled.
=============================================================================
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from src.application.services.conversation.extraction.entity_recognizer import (
    EntityRecognizer,
    get_entity_recognizer,
)
from src.application.services.conversation.followup.models import (
    FollowupConfidence,
    FollowupDetectionResult,
    FollowupType,
)
from src.application.services.conversation.normalization.normalizer import RequestNormalizer
from src.application.services.conversation.state.conversation_state import ConversationState

logger = logging.getLogger(__name__)


class LegacyFollowupFallbackDetector:
    """Legacy regex & heuristic detector used exclusively as an offline test fallback."""

    _CONTEXT_RESET_PATTERN = re.compile(
        r"^(?:new\s+question[:\s]+|forget\s+(?:the\s+)?previous(?:\s+query|\s+question)?[\s.,;:]*|"
        r"start\s+over(?:\s+and)?[\s.,;:]*|reset(?:\s+context)?[\s.,;:]*)(.+)$",
        re.IGNORECASE,
    )

    _STANDALONE_QUERY_START = re.compile(
        r"^(?:and\s+)?(?:show|list|get|find|what\s+is|what\s+are|how\s+many|display|give\s+me|select|fetch|extract|pull)\b",
        re.IGNORECASE,
    )

    _LIMIT_PATTERN = re.compile(
        r"^(?:(?:make\s+it\s+|only\s+|just\s+)?(?:show|extract|pull|get|give|fetch|take\s+(?:out\s+)?|display)?\s*(?:me\s+|us\s+)?(?:the\s+)?(?:top|first|limit\s+(?:to\s+)?)\s*(\d+|[a-zA-Z]+)(?:\s+(?:only|rows|records|items|results|customers|data|from\s+(?:the\s+)?(?:result|results|previous\s+result|table|query)|[a-zA-Z_\s]+))?)$|"
        r"^(?:top|first|limit|extract|pull)\s+(\d+|[a-zA-Z]+)(?:\s+(?:rows|records|items|results|from\s+.+|[a-zA-Z_\s]+))?$",
        re.IGNORECASE,
    )

    _GROUP_BY_PATTERN = re.compile(
        r"^(?:group(?:\s+it)?\s+by|break\s*down(?:\s+it)?\s+by|group\s+by|by)\s+([a-zA-Z_\s]+)$",
        re.IGNORECASE,
    )

    _SORT_PATTERN = re.compile(
        r"^(?:sort(?:\s+(?:that|it|them|these|those))?|order(?:\s+(?:that|it|them|these|those))?)\s*(?:by\s+)?([a-zA-Z_\s]+)?\s*(desc(?:ending)?|asc(?:ending)?|highest\s+first|lowest\s+first)?$",
        re.IGNORECASE,
    )

    _CORRECTION_PATTERN = re.compile(
        r"^(?:no[,]?\s*(?:i\s+meant\s+)?|correction[:\s]+|actually[,]?\s*|"
        r"instead\s+of\s+.+?[,]\s*show\s+|not\s+.+?[—\-,]\s*show\s+)(.+)$",
        re.IGNORECASE,
    )

    _PRONOUN_PATTERN = re.compile(
        r"\b(?:which\s+of\s+them|which\s+one|who\s+among\s+them|how\s+many\s+of\s+them|sort\s+them|order\s+them|filter\s+them)\b|"
        r"^(?:which\s+of\s+them|which\s+one|who\s+among\s+them)\b",
        re.IGNORECASE,
    )

    _FILTER_PATTERN = re.compile(
        r"^(?:only|just|filter(?:\s+by)?|keep\s+the\s+same\s+filters\s+but\s+only)\s+([a-zA-Z0-9_\s]+)$",
        re.IGNORECASE,
    )

    _SCOPE_PATTERN = re.compile(
        r"^(?:show\s+the\s+same(?:\s+thing)?\s+for|same\s+thing\s+for|what\s+about\s+for)\s+([a-zA-Z0-9_\s]+)$",
        re.IGNORECASE,
    )

    _TIME_PATTERN = re.compile(
        r"^(?:what\s+about|and|how\s+about|for|in)\s+([a-zA-Z0-9_\s]+)$",
        re.IGNORECASE,
    )

    _EXPLICIT_TIME_CHANGE_PATTERN = re.compile(
        r"^(?:change|update|replace|make)\s+(?:it|that|the\s+(?:date|year|period))\s+(?:to|for)\s+(.+)$",
        re.IGNORECASE,
    )

    _UNRESOLVED_PATTERN = re.compile(
        r"^(?:what\s+about\s+(?:it|them|that|this)|and\s+(?:it|them|that|this)|how\s+about\s+it|what\s+about\s+it)\??$",
        re.IGNORECASE,
    )

    _REFERENTIAL_SIGNAL_PATTERN = re.compile(
        r"\b(?:for\s+those\s+same|for\s+the\s+same|for\s+each\s+of\s+(?:those|them)|for\s+those|"
        r"for\s+these|for\s+the\s+[a-zA-Z0-9_]+\s+(?:above|from\s+before|previously\s+mentioned|listed\s+above)|"
        r"for\s+(?:those|these|the\s+same)\s+[a-zA-Z0-9_]+|"
        r"go\s+back\s+to\b|"
        r"from\s+before\b|as\s+before\b|mentioned\s+above\b|listed\s+above\b|"
        r"those\s+same\b|these\s+same\b|the\s+same\s+[a-zA-Z0-9_]+|"
        r"those\s+top\s+\d+|those\s+\d+|of\s+those(?:\s+top\s+\d+)?|"
        r"show\s+their\b|display\s+their\b|list\s+their\b|get\s+their\b|"
        r"\btheir\s+[a-zA-Z0-9_]+|"
        r"(?:now\s+)?show\s+only\s+[a-zA-Z0-9_]+\s+whose\b|"
        r"only\s+those\s+whose\b)\b",
        re.IGNORECASE,
    )

    _FILTER_PREPOSITIONS = {
        "in", "for", "at", "from", "with", "by", "under", "over", "between", "during", "before", "after",
    }

    def __init__(self, entity_recognizer: Optional[EntityRecognizer] = None) -> None:
        self._entity_recognizer = entity_recognizer or get_entity_recognizer()

    def is_temporal_expression(self, text: str) -> bool:
        """Determine whether text represents a temporal expression dynamically."""
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

    def extract_limit_value(self, raw_match_val: Optional[str], full_query: str) -> str:
        """Extract clean limit digit string using EntityRecognizer."""
        if raw_match_val and raw_match_val.isdigit():
            return raw_match_val
        if raw_match_val:
            num = self._entity_recognizer.extract_limit(raw_match_val, default=0)
            if num > 0:
                return str(num)
        num = self._entity_recognizer.extract_limit(full_query, default=5)
        return str(num)

    def detect_fallback(
        self,
        norm_q: str,
        has_context: bool,
    ) -> FollowupDetectionResult:
        """Execute legacy pattern matching heuristics for offline tests."""
        # Check context reset
        reset_match = self._CONTEXT_RESET_PATTERN.search(norm_q)
        if reset_match:
            clean_q = reset_match.group(1).strip()
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.INDEPENDENT,
                confidence_score=1.0,
                reason="Explicit context reset requested.",
                is_context_reset=True,
                clean_question=clean_q,
            )

        if not has_context:
            is_standalone = bool(
                self._STANDALONE_QUERY_START.search(norm_q)
                and not self._PRONOUN_PATTERN.search(norm_q)
                and not self._REFERENTIAL_SIGNAL_PATTERN.search(norm_q)
            )
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.INDEPENDENT,
                confidence_score=1.0,
                reason="Complete standalone question." if is_standalone else "No active conversation context.",
            )

        # 1. Ambiguous unresolved patterns (e.g. "What about it?", "What about that?")
        if self._UNRESOLVED_PATTERN.search(norm_q):
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.UNRESOLVED,
                confidence_score=0.4,
                reason="Ambiguous anaphoric pronoun without explicit modifier.",
            )

        # 1b. Explicit referential signals referencing previous entities/results
        if self._REFERENTIAL_SIGNAL_PATTERN.search(norm_q):
            if re.search(r"\bwhose\b", norm_q, re.IGNORECASE):
                op_type = FollowupType.FILTER_ADDITION
            else:
                op_type = FollowupType.PRONOUN_REFERENCE
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=op_type,
                target_value=norm_q,
                confidence_score=0.95,
                reason="Referential continuity signal referencing prior query scope.",
            )

        # 2. Standalone complete queries that begin with standard question words
        if (
            self._STANDALONE_QUERY_START.search(norm_q)
            and not self._PRONOUN_PATTERN.search(norm_q)
            and not self._REFERENTIAL_SIGNAL_PATTERN.search(norm_q)
        ):
            limit_match = self._LIMIT_PATTERN.search(norm_q)
            if limit_match:
                raw_num = limit_match.group(1) or limit_match.group(2)
                num = self.extract_limit_value(raw_num, norm_q)
                return FollowupDetectionResult(
                    confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                    operation_type=FollowupType.LIMIT_CHANGE,
                    target_value=num,
                    confidence_score=0.95,
                )
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.INDEPENDENT,
                confidence_score=1.0,
                reason="Complete standalone question.",
            )

        # 3. Pronoun / referential follow-up
        if self._PRONOUN_PATTERN.search(norm_q):
            sort_match = self._SORT_PATTERN.search(norm_q)
            if sort_match:
                return FollowupDetectionResult(
                    confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                    operation_type=FollowupType.SORT_CHANGE,
                    target_value=norm_q,
                    confidence_score=0.92,
                )
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.PRONOUN_REFERENCE,
                target_value=norm_q,
                confidence_score=0.92,
            )

        # 4. Correction
        corr_match = self._CORRECTION_PATTERN.search(norm_q)
        if corr_match:
            target = corr_match.group(1).strip()
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.CORRECTION,
                target_value=target,
                confidence_score=0.95,
            )

        # Explicit temporal corrections
        explicit_time_change = self._EXPLICIT_TIME_CHANGE_PATTERN.search(norm_q)
        if explicit_time_change:
            target = explicit_time_change.group(1).strip().lower()
            if self.is_temporal_expression(target):
                return FollowupDetectionResult(
                    confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                    operation_type=FollowupType.TIME_CHANGE,
                    target_value=target,
                    confidence_score=0.98,
                )

        # 5. Limit change
        limit_match = self._LIMIT_PATTERN.search(norm_q)
        if limit_match:
            raw_num = limit_match.group(1) or limit_match.group(2)
            num = self.extract_limit_value(raw_num, norm_q)
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.LIMIT_CHANGE,
                target_value=num,
                confidence_score=0.95,
            )

        # 6. Group by change
        group_match = self._GROUP_BY_PATTERN.search(norm_q)
        if group_match:
            dim = group_match.group(1).strip()
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.GROUP_BY_CHANGE,
                target_value=dim,
                confidence_score=0.95,
            )

        # 7. Sort change
        sort_match = self._SORT_PATTERN.search(norm_q)
        if sort_match:
            criteria = norm_q
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.SORT_CHANGE,
                target_value=criteria,
                confidence_score=0.9,
            )

        # 8. Filter change / addition
        filter_match = self._FILTER_PATTERN.search(norm_q)
        if filter_match:
            val = filter_match.group(1).strip()
            sub_lim = self._LIMIT_PATTERN.search(val)
            if sub_lim:
                raw_num = sub_lim.group(1) or sub_lim.group(2)
                num = self.extract_limit_value(raw_num, val)
                return FollowupDetectionResult(
                    confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                    operation_type=FollowupType.LIMIT_CHANGE,
                    target_value=num,
                    confidence_score=0.95,
                )
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.FILTER_CHANGE,
                target_value=val,
                confidence_score=0.92,
            )

        # 9. Scope change
        scope_match = self._SCOPE_PATTERN.search(norm_q)
        if scope_match:
            val = scope_match.group(1).strip()
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.SAME_QUERY_DIFFERENT_SCOPE,
                target_value=val,
                confidence_score=0.92,
            )

        # 10. Time change / Follow-up fragment
        time_match = self._TIME_PATTERN.search(norm_q)
        if time_match:
            candidate = (time_match.group(1) or "").strip().lower()

            if self._STANDALONE_QUERY_START.search(candidate):
                return FollowupDetectionResult(
                    confidence_level=FollowupConfidence.INDEPENDENT,
                    confidence_score=1.0,
                    reason="Standalone question prefixed with conversational conjunction.",
                )

            first_word = candidate.split()[0] if candidate.split() else ""
            if norm_q.startswith("and ") and first_word not in self._FILTER_PREPOSITIONS:
                is_time = self.is_temporal_expression(candidate)
                if not is_time:
                    return FollowupDetectionResult(
                        confidence_level=FollowupConfidence.UNRESOLVED,
                        confidence_score=0.5,
                        reason=f"Ambiguous entity reference '{candidate}'. Clarification required.",
                    )

            if self.is_temporal_expression(candidate):
                return FollowupDetectionResult(
                    confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                    operation_type=FollowupType.TIME_CHANGE,
                    target_value=candidate,
                    confidence_score=0.95,
                )

            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.FILTER_CHANGE,
                target_value=candidate,
                confidence_score=0.88,
            )

        # 11. Standalone month/year or entity query: e.g. "February", "2024"
        if self.is_temporal_expression(norm_q):
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.TIME_CHANGE,
                target_value=norm_q,
                confidence_score=0.9,
            )

        # 12. Default: independent query
        return FollowupDetectionResult(
            confidence_level=FollowupConfidence.INDEPENDENT,
            confidence_score=1.0,
            reason="Query does not contain continuation markers.",
        )
