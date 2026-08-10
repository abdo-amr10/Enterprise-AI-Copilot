"""Maps normalized schema metadata into semantic-layer build inputs."""
from typing import Any


class SchemaMapper:
    """Provides small, deterministic mappings used during ingestion."""

    def map_tables(self, schema: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"table": name, "columns": table.get("columns", [])}
            for name, table in schema.get("tables", {}).items()
        ]

    def map_relationships(self, relationships: dict[str, Any]) -> list[dict[str, Any]]:
        return relationships.get("relationships", [])

    def map_join_paths(self, relationships: dict[str, Any]) -> list[dict[str, Any]]:
        return relationships.get("join_paths", [])
