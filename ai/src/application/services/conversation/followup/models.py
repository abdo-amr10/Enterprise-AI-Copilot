"""Follow-up operation types and confidence outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FollowupType(str, Enum):
    FILTER_CHANGE = "FILTER_CHANGE"
    FILTER_ADDITION = "FILTER_ADDITION"
    FILTER_REMOVAL = "FILTER_REMOVAL"
    TIME_CHANGE = "TIME_CHANGE"
    LIMIT_CHANGE = "LIMIT_CHANGE"
    SORT_CHANGE = "SORT_CHANGE"
    GROUP_BY_CHANGE = "GROUP_BY_CHANGE"
    METRIC_CHANGE = "METRIC_CHANGE"
    ENTITY_CHANGE = "ENTITY_CHANGE"
    CLARIFICATION = "CLARIFICATION"
    CORRECTION = "CORRECTION"
    SAME_QUERY_DIFFERENT_SCOPE = "SAME_QUERY_DIFFERENT_SCOPE"


class FollowupConfidence(str, Enum):
    FOLLOW_UP_CONFIRMED = "FOLLOW_UP_CONFIRMED"
    FOLLOW_UP_POSSIBLE = "FOLLOW_UP_POSSIBLE"
    INDEPENDENT = "INDEPENDENT"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class FollowupDetectionResult:
    confidence_level: FollowupConfidence
    operation_type: Optional[FollowupType] = None
    target_value: Optional[str] = None
    target_key: Optional[str] = None
    confidence_score: float = 1.0
    referenced_turn_id: Optional[str] = None
    reason: Optional[str] = None

    @property
    def is_followup(self) -> bool:
        return self.confidence_level in (
            FollowupConfidence.FOLLOW_UP_CONFIRMED,
            FollowupConfidence.FOLLOW_UP_POSSIBLE,
        )
