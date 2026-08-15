import pytest

from src.infrastructure.semantic_layer.ingestion.schema_loader import SchemaLoader


class TestSchemaLoader:
    """
    Unit tests for the SchemaLoader component.

    These tests verify that schema metadata is correctly loaded,
    normalized, and validated before being used by the Semantic Layer.
    """

    def test_load_normalizes_schema(self):
        """
        Verify that a valid schema is loaded with its metadata,
        tables, and column definitions preserved correctly.
        """
        schema = {
            "version": "1.0",
            "database": "Synthetic Banking Database",
            "source": "Database Test Schema.pdf",
            "tables": {
                "customers": {
                    "columns": [
                        {
                            "name": "customer_id",
                            "type": "varchar(20)",
                            "primary_key": True,
                        },
                        {
                            "name": "first_name",
                            "type": "varchar(50)",
                            "primary_key": False,
                        },
                    ]
                }
            },
        }

        result = SchemaLoader().load(schema)

        assert result["version"] == "1.0"
        assert result["database"] == "Synthetic Banking Database"
        assert result["source"] == "Database Test Schema.pdf"

        assert "customers" in result["tables"]

        columns = result["tables"]["customers"]["columns"]

        assert columns[0] == {
            "name": "customer_id",
            "type": "varchar(20)",
            "primary_key": True,
        }

        assert columns[1] == {
            "name": "first_name",
            "type": "varchar(50)",
            "primary_key": False,
        }

    def test_load_uses_default_version_when_missing(self):
        """
        Verify that the loader assigns the default schema version
        when the version field is not provided.
        """
        schema = {
            "database": "Synthetic Banking Database",
            "tables": {
                "customers": {
                    "columns": []
                }
            }
        }

        result = SchemaLoader().load(schema)

        assert result["version"] == "1.0"

    def test_load_rejects_missing_tables(self):
        """
        Verify that loading fails when the required tables field
        is missing from the schema.
        """
        schema = {
            "version": "1.0",
            "database": "Synthetic Banking Database",
        }

        with pytest.raises(
            ValueError,
            match="Schema is missing required field: 'tables'",
        ):
            SchemaLoader().load(schema)

    def test_load_defaults_primary_key_to_false(self):
        """
        Verify that the primary_key field defaults to False
        when it is not explicitly provided for a column.
        """
        schema = {
            "version": "1.0",
            "database": "Synthetic Banking Database",
            "tables": {
                "customers": {
                    "columns": [
                        {
                            "name": "first_name",
                            "type": "varchar(50)",
                        }
                    ]
                }
            },
        }

        result = SchemaLoader().load(schema)

        assert (
            result["tables"]["customers"]["columns"][0]["primary_key"]
            is False
        )
