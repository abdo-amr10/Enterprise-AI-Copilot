"""Unit tests for SchemaMapper.

These tests verify that normalized schema and relationship metadata
are mapped into semantic-layer build inputs without modification
or inferred metadata.
"""

from ai.src.infrastructure.semantic_layer.ingestion.schema_mapper import SchemaMapper


class TestSchemaMapper:
    """Tests for deterministic schema-to-builder mapping."""

    def test_map_tables_preserves_table_and_column_metadata(self):
        """Map normalized tables without changing their metadata."""
        schema = {
            "tables": {
                "customers": {
                    "columns": [
                        {
                            "name": "customer_id",
                            "type": "varchar(20)",
                            "primary_key": True,
                        }
                    ]
                }
            }
        }

        result = SchemaMapper().map_tables(schema)

        assert result == [
            {
                "table": "customers",
                "columns": [
                    {
                        "name": "customer_id",
                        "type": "varchar(20)",
                        "primary_key": True,
                    }
                ],
            }
        ]

    def test_map_relationships_preserves_explicit_relationships(self):
        """Return explicitly defined relationships without modification."""
        relationships = {
            "relationships": [
                {
                    "name": "customers_accounts",
                    "from_table": "customers",
                    "from_column": "customer_id",
                    "to_table": "accounts",
                    "to_column": "customer_id",
                    "cardinality": "1:N",
                    "relationship_type": "foreign_key",
                }
            ]
        }

        result = SchemaMapper().map_relationships(relationships)

        assert result == relationships["relationships"]

    def test_map_join_paths_returns_empty_list_when_not_provided(self):
        """Return no join paths when the source does not define any."""
        relationships = {
            "relationships": []
        }

        result = SchemaMapper().map_join_paths(relationships)

        assert result == []