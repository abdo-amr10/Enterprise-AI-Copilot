"""Unit tests for JsonSchemaRepository."""

import json

from ai.src.infrastructure.semantic_layer.ingestion.json_schema_repository import (
    JsonSchemaRepository,
)


class TestJsonSchemaRepository:
    """Tests for reading the required source schema."""

    def test_load_returns_parsed_schema(self, tmp_path):
        """Return the parsed JSON content from the schema file."""
        schema = {
            "version": "1.0",
            "database": "Synthetic Banking Database",
            "tables": {
                "customers": {
                    "columns": []
                }
            },
        }

        schema_path = tmp_path / "schema.json"
        schema_path.write_text(
            json.dumps(schema),
            encoding="utf-8",
        )

        result = JsonSchemaRepository(schema_path).load()

        assert result == schema