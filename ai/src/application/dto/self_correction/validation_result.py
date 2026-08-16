"""Outcome of a single deterministic validator run."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.application.dto.self_correction.validation_issue import ValidationIssue


@dataclass(frozen=True)
class ValidationResult:
    """Result of a deterministic (non-LLM) validation step.

    Deterministic validators are the final authority in the self-
    correction pipeline: they never guess and never defer to the LLM
    for their own decision.
    """

    is_valid: bool
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(is_valid=True, issues=())

    @classmethod
    def fail(cls, issues: list[ValidationIssue]) -> "ValidationResult":
        if not issues:
            raise ValueError("A failing ValidationResult requires at least one issue.")
        return cls(is_valid=False, issues=tuple(issues))
