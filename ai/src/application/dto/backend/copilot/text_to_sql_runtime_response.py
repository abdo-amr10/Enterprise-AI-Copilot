"""Internal AI-runtime response consumed by the Backend before RLS/execution."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextToSQLRuntimeResponse:
    status: str
    sql: str | None
    error_code: str | None = None
    message: str | None = None
    failure_reason: str | None = None
    rewritten_question: str | None = None
    suggestions: tuple[str, ...] = ()

    @classmethod
    def success(cls, sql: str) -> "TextToSQLRuntimeResponse":
        return cls(status="Success", sql=sql)

    @classmethod
    def failure(
        cls,
        error_code: str,
        message: str,
        *,
        failure_reason: str | None = None,
        rewritten_question: str | None = None,
        suggestions: tuple[str, ...] = (),
    ) -> "TextToSQLRuntimeResponse":
        return cls(
            status="Failed",
            sql=None,
            error_code=error_code,
            message=message,
            failure_reason=failure_reason,
            rewritten_question=rewritten_question,
            suggestions=suggestions,
        )
