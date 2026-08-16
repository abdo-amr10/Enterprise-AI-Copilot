"""Application port for the physical schema used in SQL validation."""

from __future__ import annotations

from typing import Any, Protocol


class PhysicalSchemaRepository(Protocol):
    """Provides normalized physical database metadata without exposing storage."""

    def get_schema(self) -> dict[str, Any]:
        """Return the normalized physical schema used for validation."""
