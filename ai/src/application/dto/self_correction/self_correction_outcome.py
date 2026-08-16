"""Final outcome of the Self-Correction loop."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SelfCorrectionOutcome:
    """Result returned by SelfCorrectionService.run().

    This is intentionally minimal: CopilotRuntimePipeline only needs
    to know whether a validated SQL string is available, and, if not,
    that correction was exhausted so it can map the outcome onto the
    Backend's standard error contract (MAX_RETRIES_EXCEEDED).
    """

    is_valid: bool
    sql: str | None
    attempts_used: int

    @classmethod
    def success(cls, sql: str, attempts_used: int) -> "SelfCorrectionOutcome":
        return cls(is_valid=True, sql=sql, attempts_used=attempts_used)

    @classmethod
    def failure(cls, attempts_used: int) -> "SelfCorrectionOutcome":
        return cls(is_valid=False, sql=None, attempts_used=attempts_used)
