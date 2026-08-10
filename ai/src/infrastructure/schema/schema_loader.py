"""Schema normalization at dataset-ingestion time."""
from typing import Any


class SchemaLoader:
    """Normalizes raw schema metadata into a stable internal shape."""

    def load(self, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": schema.get("version", "1.0"),
            "database": schema.get("database"),
            "source": schema.get("source"),
            "tables": self._load_tables(schema.get("tables", {})),
        }

    @staticmethod
    def _load_tables(tables: dict[str, Any]) -> dict[str, Any]:
        normalized = {}

        for table_name, table in tables.items():
            normalized[table_name] = {
                "columns": [
                    {
                        "name": column["name"],
                        "type": column.get("type"),
                        "primary_key": bool(column.get("primary_key", False)),
                    }
                    for column in table.get("columns", [])
                ]
            }

        return normalized
