"""Deterministic follow-up detector operating without calling the main LLM."""

from __future__ import annotations

import re
from typing import Optional

from src.application.services.conversation.followup.models import (
    FollowupConfidence,
    FollowupDetectionResult,
    FollowupType,
)
from src.application.services.conversation.normalization.normalizer import RequestNormalizer
from src.application.services.conversation.state.conversation_state import ConversationState


class FollowupDetector:
    """Classifies follow-up operations deterministically using structural patterns."""

    _MONTHS_AND_PERIODS = {
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "last year", "last month", "this year", "this month", "q1", "q2", "q3", "q4",
    }

    _LIMIT_PATTERN = re.compile(
        r"^(?:make\s+it\s+)?(?:top|first|limit\s+to|only)\s+(\d+)$|"
        r"^(?:top|first)\s+(\d+)$",
        re.IGNORECASE,
    )

    _GROUP_BY_PATTERN = re.compile(
        r"^(?:group(?:\s+it)?\s+by|break\s*down(?:\s+it)?\s+by|group\s+by|by)\s+([a-zA-Z_\s]+)$",
        re.IGNORECASE,
    )

    _SORT_PATTERN = re.compile(
        r"^(?:sort(?:\s+(?:that|it))?|order(?:\s+(?:that|it))?)\s*(?:by\s+)?([a-zA-Z_\s]+)?\s*(desc(?:ending)?|asc(?:ending)?|highest\s+first|lowest\s+first)?$",
        re.IGNORECASE,
    )

    _CORRECTION_PATTERN = re.compile(
        r"^(?:no[,،]?\s*(?:i\s+meant\s+)?|correction[:\s]+)(.+)$",
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
        r"^(?:change|update|replace|make)\s+(?:it|that|the\s+(?:date|year|period))\s+(?:to|for)\s+"
        r"(january|february|march|april|may|june|july|august|september|october|november|december|\d{4}|last\s+year|last\s+month|this\s+year|this\s+month|q[1-4])$",
        re.IGNORECASE,
    )

    _UNRESOLVED_PATTERN = re.compile(
        r"^(?:what\s+about\s+(?:it|them|that|this)|and\s+(?:it|them|that|this)|how\s+about\s+it|what\s+about\s+it)\??$",
        re.IGNORECASE,
    )

    def detect(
        self,
        question: str,
        state: Optional[ConversationState] = None,
        has_history: bool = False,
    ) -> FollowupDetectionResult:
        """Detect follow-up operations deterministically."""
        norm_q = RequestNormalizer.normalize(question)

        # If no previous context or history, query is independent
        has_context = has_history or (state is not None and (
            state.active_query_state is not None or state.last_successful_execution is not None
        ))

        if not has_context:
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.INDEPENDENT,
                confidence_score=1.0,
                reason="No active conversation context.",
            )

        # 1. Ambiguous unresolved patterns (e.g. "What about it?", "What about that?")
        if self._UNRESOLVED_PATTERN.search(norm_q):
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.UNRESOLVED,
                confidence_score=0.4,
                reason="Ambiguous anaphoric pronoun without explicit modifier.",
            )

        # 2. Correction (e.g. "No, I meant Cairo", "No, February")
        corr_match = self._CORRECTION_PATTERN.search(norm_q)
        if corr_match:
            target = corr_match.group(1).strip()
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.CORRECTION,
                target_value=target,
                confidence_score=0.95,
            )

        # Explicit temporal corrections are follow-ups, not independent
        # questions.  The narrow grammar prevents unrelated requests from
        # inheriting state accidentally.
        explicit_time_change = self._EXPLICIT_TIME_CHANGE_PATTERN.search(norm_q)
        if explicit_time_change:
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.TIME_CHANGE,
                target_value=explicit_time_change.group(1).strip().lower(),
                confidence_score=0.98,
            )

        # 3. Limit change (e.g. "Make it top 5", "top 10")
        limit_match = self._LIMIT_PATTERN.search(norm_q)
        if limit_match:
            num = limit_match.group(1) or limit_match.group(2)
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.LIMIT_CHANGE,
                target_value=num,
                confidence_score=0.95,
            )

        # 4. Group by change (e.g. "Group it by region", "by department")
        group_match = self._GROUP_BY_PATTERN.search(norm_q)
        if group_match:
            dim = group_match.group(1).strip()
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.GROUP_BY_CHANGE,
                target_value=dim,
                confidence_score=0.95,
            )

        # 5. Sort change (e.g. "Sort by total descending")
        sort_match = self._SORT_PATTERN.search(norm_q)
        if sort_match:
            criteria = norm_q
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.SORT_CHANGE,
                target_value=criteria,
                confidence_score=0.9,
            )

        # 6. Filter change / addition (e.g. "Only Cairo", "only managers")
        filter_match = self._FILTER_PATTERN.search(norm_q)
        if filter_match:
            val = filter_match.group(1).strip()
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.FILTER_CHANGE,
                target_value=val,
                confidence_score=0.92,
            )

        # 7. Scope change (e.g. "Show the same thing for Alexandria")
        scope_match = self._SCOPE_PATTERN.search(norm_q)
        if scope_match:
            val = scope_match.group(1).strip()
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.SAME_QUERY_DIFFERENT_SCOPE,
                target_value=val,
                confidence_score=0.92,
            )

        # 8. Time change (e.g. "What about February?", "What about 2024?", "in 2025")
        time_match = self._TIME_PATTERN.search(norm_q)
        if time_match:
            candidate = time_match.group(1).strip().lower()
            # If candidate is a known month, year (\d{4}), or time period:
            if candidate in self._MONTHS_AND_PERIODS or re.match(r"^\d{4}$", candidate):
                return FollowupDetectionResult(
                    confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                    operation_type=FollowupType.TIME_CHANGE,
                    target_value=candidate,
                    confidence_score=0.95,
                )
            # General "What about X" might be a filter or entity change
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.FILTER_CHANGE,
                target_value=candidate,
                confidence_score=0.88,
            )

        # 9. Standalone month/year or entity query: e.g. "February", "2024"
        if norm_q in self._MONTHS_AND_PERIODS or re.match(r"^\d{4}$", norm_q):
            return FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=FollowupType.TIME_CHANGE,
                target_value=norm_q,
                confidence_score=0.9,
            )

        # 10. Default: independent query
        return FollowupDetectionResult(
            confidence_level=FollowupConfidence.INDEPENDENT,
            confidence_score=1.0,
            reason="Query does not contain continuation markers.",
        )
