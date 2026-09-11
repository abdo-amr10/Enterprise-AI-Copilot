"""Schema normalization and validation at dataset-ingestion time."""

from __future__ import annotations

from typing import Any

from src.application.services.semantic_layer.relationships.models import (
    BackendDatabaseSchema,
)
from src.application.services.semantic_layer.relationships.relationship_service import (
    RelationshipProcessingEngine,
    RelationshipProcessingResult,
)


class SchemaLoader:
    """Validates and normalizes the required source database schema.

    Input:
        A raw schema dictionary loaded from the dataset metadata.

    Output:
        A normalized schema dictionary containing the database metadata,
        table definitions, columns, data types, and primary-key information.

    Notes:
        The source schema is required and must not be inferred or completed
        with generated business information.
    """

    REQUIRED_FIELDS = ("database", "tables")

    def __init__(self) -> None:
        self._relationship_engine = RelationshipProcessingEngine()

    def load(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize the source schema.

        Args:
            schema: Raw schema metadata from the dataset.

        Returns:
            A normalized schema representation.

        Raises:
            ValueError: If the schema is missing required metadata.
        """
        self._validate_schema(schema)

        return {
            "version": schema.get("version") or "1.0",
            "database": schema["database"],
            "source": schema.get("source"),
            "tables": self._load_tables(schema["tables"]),
            "relationships": schema.get("relationships", []),
        }

    def process_schema_and_relationships(
        self,
        schema: dict[str, Any],
        explicit_relationships: list[dict[str, Any]] | None = None,
        sample_data: Any | None = None,
        glossary_terms: list[str] | None = None,
    ) -> RelationshipProcessingResult:
        """Process schema and relationships through the full Relationship Engine."""
        return self._relationship_engine.process(
            raw_schema=schema,
            explicit_relationships=explicit_relationships,
            sample_data=sample_data,
            glossary_terms=glossary_terms,
        )

    @classmethod
    def _validate_schema(cls, schema: dict[str, Any]) -> None:
        """Validate required schema metadata using Pydantic."""
        if not isinstance(schema, dict):
            raise ValueError("Schema must be a dictionary.")

        for field in cls.REQUIRED_FIELDS:
            if field not in schema:
                raise ValueError(
                    f"Schema is missing required field: '{field}'."
                )

        if not schema["database"]:
            raise ValueError("Schema must contain a database name.")

        if not isinstance(schema["tables"], dict) or not schema["tables"]:
            raise ValueError("Schema must contain at least one table.")

        relationships = schema.get("relationships", [])
        if not isinstance(relationships, list):
            raise ValueError("Schema relationships must be a list.")

        # Full Pydantic structural validation
        try:
            BackendDatabaseSchema.model_validate(schema)
        except Exception as error:
            # Propagate clear validation message
            raise ValueError(f"Schema validation failed: {error}") from error

    @staticmethod
    def _load_tables(
        tables: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalize table and column metadata."""
        normalized: dict[str, Any] = {}

        for table_name, table in tables.items():
            if not isinstance(table, dict):
                raise ValueError(
                    f"Table '{table_name}' must be an object."
                )

            columns = table.get("columns", [])

            if not isinstance(columns, list):
                raise ValueError(
                    f"Columns for table '{table_name}' must be a list."
                )

            normalized[table_name] = {
                "columns": [
                    {
                        "name": column["name"],
                        "type": column.get("type"),
                        "primary_key": bool(
                            column.get("primary_key", False)
                        ),
                    }
                    for column in columns
                ]
            }

        return normalized