"""Maps normalized source metadata into semantic-layer build inputs."""

from typing import Any


class SchemaMapper:
    """Maps normalized schema and relationship metadata.

    Input:
        A normalized schema dictionary and, when available,
        relationship metadata.

    Output:
        Stable lists of tables and relationships 
        for semantic-layer construction.

    The mapper does not invent, infer, or modify source metadata.
    """

    def map_tables(self, schema: dict[str, Any]) -> list[dict[str, Any]]:
        """Map normalized tables into semantic-layer build inputs."""
        return [
            {
                "table": table_name,
                "columns": table.get("columns", []),
            }
            for table_name, table in schema.get("tables", {}).items()
        ]

    def map_relationships(
        self, relationships: list[dict[str, Any]] | dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Return explicit relationships without inferring any new ones."""
        if isinstance(relationships, dict):
            relationships = relationships.get("relationships", [])
        if not isinstance(relationships, list):
            raise ValueError("relationships must be a list or schema object.")
        return relationships

    def map_join_paths(self, schema: dict[str, Any]) -> list[dict[str, Any]]:
        """Return supplied join paths only; never derive them automatically."""
        join_paths = schema.get("join_paths", [])
        if not isinstance(join_paths, list):
            raise ValueError("join_paths must be a list when provided.")
        return join_paths

   
