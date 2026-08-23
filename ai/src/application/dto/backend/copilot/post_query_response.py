"""AI-formatted representation of a Backend execution result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PostQueryResponse:
    status: str
    presentation_type: str
    text: str
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    row_count: int = 0
    file_name: str | None = None
    content_type: str | None = None
    file_content_base64: str | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status,
            "presentationType": self.presentation_type,
            "text": self.text,
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
            "rowCount": self.row_count,
        }
        if self.file_name:
            result["fileName"] = self.file_name
            result["contentType"] = self.content_type
            result["fileContentBase64"] = self.file_content_base64
        if self.error_code:
            result["errorCode"] = self.error_code
        return result
