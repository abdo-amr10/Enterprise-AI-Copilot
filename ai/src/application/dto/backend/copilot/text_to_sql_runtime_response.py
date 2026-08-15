"""Internal AI-runtime response consumed by the Backend before RLS/execution."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextToSQLRuntimeResponse:
    status: str
    sql: str | None
    error_code: str | None = None
    message: str | None = None

    @classmethod
    def success(cls, sql: str) -> "TextToSQLRuntimeResponse":
        return cls(status="Success", sql=sql)

    @classmethod
    def failure(
        cls, error_code: str, message: str
    ) -> "TextToSQLRuntimeResponse":
        return cls(
            status="Failed",
            sql=None,
            error_code=error_code,
            message=message,
        )
