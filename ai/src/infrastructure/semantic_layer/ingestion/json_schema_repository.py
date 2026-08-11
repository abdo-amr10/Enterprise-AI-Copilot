"""JSON adapter for reading the required source schema during ingestion."""

import json
from pathlib import Path
from typing import Any


class JsonSchemaRepository:
    """Reads the required source schema from a JSON file.

    Input:
        A filesystem path pointing to the source schema JSON file.

    Output:
        The parsed JSON content as a dictionary.

    Responsibility:
        This class only handles file I/O. Schema validation and
        normalization are handled by SchemaLoader.
    """

    def __init__(self, schema_path: str | Path) -> None:
        """Initialize the repository.

        Args:
            schema_path: Path to the required source schema JSON file.
        """
        self._schema_path = Path(schema_path)

    def load(self) -> dict[str, Any]:
        """Load and parse the source schema.

        Returns:
            The parsed schema metadata.

        Raises:
            FileNotFoundError: If the schema file does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        with self._schema_path.open(encoding="utf-8") as file:
            return json.load(file)