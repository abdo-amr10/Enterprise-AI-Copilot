"""Structured diagnosis returned by the SQL Critic LLM call.

The critic never returns SQL and never decides validity on its own.
It only reports candidate issues, each of which is later checked
against the approved schema/relationships by CriticFindingVerifier
before it is allowed to influence correction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN"})


@dataclass(frozen=True)
class CriticIssue:
    type: str
    description: str
    evidence: str | None = None


@dataclass(frozen=True)
class CriticResult:
    status: str
    issues: tuple[CriticIssue, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}.")

    @property
    def passed(self) -> bool:
        return self.status == "PASS"
