"""Application use case for activating a prepared semantic layer."""
from typing import Any

from src.application.ports.schema_repository import SchemaRepository


class SemanticLayerBuildService:
    """Coordinates dataset-load validation and semantic-layer activation.

    The actual filesystem/index implementations stay in infrastructure.
    """

    def __init__(self, schema_repository: SchemaRepository, semantic_loader: Any) -> None:
        self._schema_repository = schema_repository
        self._semantic_loader = semantic_loader

    def activate(self, source_semantic_root: str) -> None:
        schema = self._schema_repository.load()
        self._validate_schema(schema)
        self._semantic_loader.replace(source_semantic_root)

    @staticmethod
    def _validate_schema(schema: dict[str, Any]) -> None:
        if not schema.get("database"):
            raise ValueError("Schema must contain a database name.")
        if not schema.get("tables"):
            raise ValueError("Schema must contain tables.")
