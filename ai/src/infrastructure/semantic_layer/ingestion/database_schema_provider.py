"""Filesystem adapter for the physical database schema validation port."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.infrastructure.semantic_layer.ingestion.schema_loader import SchemaLoader


class DatabaseSchemaProvider:
    """Load and cache normalized physical schema metadata from a local artifact."""

    def __init__(self, schema_path: str | Path) -> None:
        self._schema_path = Path(schema_path)
        self._schema: dict[str, Any] | None = None

    def get_schema(self) -> dict[str, Any]:
        if self._schema is None:
            with self._schema_path.open(encoding="utf-8") as source:
                raw_schema = json.load(source)
            self._schema = SchemaLoader().load(raw_schema)
        return self._schema
