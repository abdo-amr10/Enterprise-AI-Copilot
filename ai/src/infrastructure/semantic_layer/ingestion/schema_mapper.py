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

    def map_relationships( self,relationships: list[dict[str, Any]],) -> list[dict[str, Any]]:
        """Return explicitly defined relationships without modification."""
        return relationships

   