"""JSON implementation of the schema repository."""
import json
from pathlib import Path
from typing import Any


class JsonSchemaRepository:
    """Reads the source schema during dataset ingestion only."""

    def __init__(self, schema_path: str | Path) -> None:
        self._schema_path = Path(schema_path)

    def load(self) -> dict[str, Any]:
        with self._schema_path.open(encoding="utf-8") as file:
            return json.load(file)
