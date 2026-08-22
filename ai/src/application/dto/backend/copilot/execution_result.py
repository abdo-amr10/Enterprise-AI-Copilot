"""Storage-neutral Backend-to-AI execution-result contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BackendExecutionResult:
    """The result returned by Backend after it executes validated SQL.

    This DTO deliberately carries values only. It never exposes a database
    cursor, driver object, connection, or authorization detail to the AI.
    """

    status: str
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    row_count: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"Success", "Failed"}:
            raise ValueError("status must be Success or Failed.")
        if self.status == "Failed" and not self.error_message:
            raise ValueError("error_message is required for a failed execution.")
        if len(set(self.columns)) != len(self.columns) or any(not value.strip() for value in self.columns):
            raise ValueError("columns must contain unique non-empty names.")
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("every row must have one value per column.")
        if self.row_count is not None and self.row_count < 0:
            raise ValueError("row_count cannot be negative.")
        if self.row_count is not None and self.row_count != len(self.rows):
            raise ValueError("row_count must match the complete rows payload.")

    @property
    def effective_row_count(self) -> int:
        return self.row_count if self.row_count is not None else len(self.rows)
