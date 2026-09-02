"""Schema Normalizer: Normalizes identifiers for matching while preserving exact physical database names."""

from __future__ import annotations

import re
from typing import Any
from src.application.services.semantic_layer.relationships.models import (
    BackendDatabaseSchema,
    NormalizedColumn,
    NormalizedSchema,
    NormalizedTable,
)


class SchemaNormalizer:
    """Normalizes schema identifiers for evidence matching without altering physical names."""

    @staticmethod
    def normalize_identifier(name: str) -> str:
        """Convert any identifier (camelCase, PascalCase, kebab-case, UPPERCASE) to standard snake_case.

        Examples:
            CustomerID -> customer_id
            customer_id -> customer_id
            CUSTOMER_ID -> customer_id
            Customer_Id -> customer_id
            order-details -> order_details
            tblCustomers -> tbl_customers
        """
        if not name:
            return ""

        s = name.strip()
        # Handle dot prefix if schema name is included (e.g., dbo.customers -> customers for local matching)
        if "." in s:
            s = s.split(".")[-1]

        # Insert underscore before capital letters preceded by lowercase letter or digit
        s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
        # Insert underscore between consecutive capitals followed by lowercase (e.g., HTTPResponse -> http_response)
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
        # Replace non-alphanumeric chars (dashes, spaces) with underscores
        s = re.sub(r"[\s\-]+", "_", s)
        # Collapse multiple underscores
        s = re.sub(r"_+", "_", s)
        return s.strip("_").casefold()

    @classmethod
    def normalize_schema(cls, schema: BackendDatabaseSchema) -> NormalizedSchema:
        """Create a normalized internal representation of the backend schema."""
        normalized_tables: dict[str, NormalizedTable] = {}

        for raw_table_name, table_def in schema.tables.items():
            norm_table_name = cls.normalize_identifier(raw_table_name)
            normalized_columns: dict[str, NormalizedColumn] = {}

            for col in table_def.columns:
                norm_col_name = cls.normalize_identifier(col.name)
                normalized_columns[col.name] = NormalizedColumn(
                    original_name=col.name,
                    normalized_name=norm_col_name,
                    data_type=col.type,
                    is_primary_key=col.primary_key,
                    nullable=col.nullable,
                    unique=col.unique,
                )

            normalized_tables[raw_table_name] = NormalizedTable(
                original_name=raw_table_name,
                normalized_name=norm_table_name,
                columns=normalized_columns,
            )

        return NormalizedSchema(
            database=schema.database,
            version=schema.version,
            source=schema.source,
            tables=normalized_tables,
        )

    @classmethod
    def find_table_by_name(cls, schema: NormalizedSchema, name: str) -> NormalizedTable | None:
        """Find a table by exact original name, or fallback to normalized name."""
        if name in schema.tables:
            return schema.tables[name]
        
        target_norm = cls.normalize_identifier(name)
        for table in schema.tables.values():
            if table.normalized_name == target_norm:
                return table
        return None

    @classmethod
    def find_column_by_name(cls, table: NormalizedTable, name: str) -> NormalizedColumn | None:
        """Find a column by exact original name, or fallback to normalized name."""
        if name in table.columns:
            return table.columns[name]
        
        target_norm = cls.normalize_identifier(name)
        for col in table.columns.values():
            if col.normalized_name == target_norm:
                return col
        return None
