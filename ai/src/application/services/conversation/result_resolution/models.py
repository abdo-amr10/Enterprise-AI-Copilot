"""Result resolution status and outcome contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ResultResolutionStatus(str, Enum):
    ANSWERABLE = "ANSWERABLE"
    NOT_ANSWERABLE = "NOT_ANSWERABLE"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID_RESULT_REFERENCE = "INVALID_RESULT_REFERENCE"


@dataclass(frozen=True)
class ResultResolutionOutcome:
    status: ResultResolutionStatus
    answer: Optional[str] = None
    confidence: float = 0.0
    referenced_column: Optional[str] = None
    referenced_row_index: Optional[int] = None
    reason: Optional[str] = None

    @property
    def message(self) -> Optional[str]:
        return self.reason

    @classmethod
    def answerable(
        cls,
        answer: str,
        *,
        confidence: float = 1.0,
        column: Optional[str] = None,
        row_index: Optional[int] = None,
    ) -> ResultResolutionOutcome:
        return cls(
            status=ResultResolutionStatus.ANSWERABLE,
            answer=answer,
            confidence=confidence,
            referenced_column=column,
            referenced_row_index=row_index,
        )

    @classmethod
    def not_answerable(cls, reason: str) -> ResultResolutionOutcome:
        return cls(
            status=ResultResolutionStatus.NOT_ANSWERABLE,
            confidence=1.0,
            reason=reason,
        )

    @classmethod
    def ambiguous(cls, reason: str) -> ResultResolutionOutcome:
        return cls(
            status=ResultResolutionStatus.AMBIGUOUS,
            confidence=0.5,
            reason=reason,
        )

    @classmethod
    def invalid_reference(cls, reason: str) -> ResultResolutionOutcome:
        return cls(
            status=ResultResolutionStatus.INVALID_RESULT_REFERENCE,
            confidence=1.0,
            reason=reason,
        )
