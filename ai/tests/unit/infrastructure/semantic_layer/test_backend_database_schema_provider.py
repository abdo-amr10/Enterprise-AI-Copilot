"""Tests for BackendDatabaseSchemaProvider in-memory caching and version safety."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from src.infrastructure.semantic_layer.ingestion.backend_database_schema_provider import (
    BackendDatabaseSchemaProvider,
)


def test_schema_provider_caches_in_memory_by_schema_file_id():
    client = MagicMock()
    client.get_status.return_value = {
        "status": "Approved",
        "sources": {"schemaFileId": "file-schema-101"},
    }
    client._get.return_value = {
        "content": {
            "database": "ERP_DB",
            "tables": {
                "customers": {"columns": [{"name": "id", "type": "int"}]}
            }
        }
    }

    provider = BackendDatabaseSchemaProvider(client=client)

    assert provider.cached_schema_file_id is None

    # First call: fetches from client and parses
    schema1 = provider.get_schema()
    assert provider.cached_schema_file_id == "file-schema-101"
    assert "customers" in schema1.get("tables", {})
    assert client.get_status.call_count == 1
    assert client._get.call_count == 1

    # Second call: uses cached schema in memory without re-fetching file!
    schema2 = provider.get_schema()
    assert schema2 is schema1
    assert client._get.call_count == 1  # File was NOT downloaded again!

    # When schemaFileId changes (new file uploaded in Backend):
    client.get_status.return_value = {
        "status": "Approved",
        "sources": {"schemaFileId": "file-schema-102"},
    }
    client._get.return_value = {
        "content": {
            "database": "ERP_DB",
            "tables": {
                "orders": {"columns": [{"name": "order_id", "type": "int"}]}
            }
        }
    }

    # Automatically invalidates and fetches the new version
    schema3 = provider.get_schema()
    assert provider.cached_schema_file_id == "file-schema-102"
    assert "orders" in schema3.get("tables", {})
    assert client._get.call_count == 2  # Fetched the new schema version


def test_schema_provider_invalidate_clears_cache():
    client = MagicMock()
    client.get_status.return_value = {
        "status": "Approved",
        "sources": {"schemaFileId": "file-schema-101"},
    }
    client._get.return_value = {
        "content": {
            "database": "ERP_DB",
            "tables": {
                "customers": {"columns": [{"name": "id", "type": "int"}]}
            }
        }
    }

    provider = BackendDatabaseSchemaProvider(client=client)
    provider.get_schema()
    assert provider.cached_schema_file_id == "file-schema-101"

    provider.invalidate()
    assert provider.cached_schema_file_id is None
    assert provider.cached_revision_id is None


def test_schema_provider_caches_in_memory_by_active_revision_id():
    client = MagicMock()
    client.get_status.return_value = {
        "status": "Approved",
        "revisionId": "rev-101",
    }
    client.get_active_revision_schema.return_value = {
        "semanticLayerId": "layer-001",
        "revisionId": "rev-101",
        "status": "Approved",
        "schema": {
            "database": "ERP_DB",
            "tables": {
                "accounts": {"columns": [{"name": "account_id", "type": "int"}]}
            },
        },
    }

    provider = BackendDatabaseSchemaProvider(client=client)
    assert provider.cached_revision_id is None

    # First call: fetches from active revision schema endpoint
    schema1 = provider.get_schema()
    assert provider.cached_revision_id == "rev-101"
    assert "accounts" in schema1.get("tables", {})
    assert client.get_active_revision_schema.call_count == 1

    # Second call: uses cached schema in memory without re-calling client
    schema2 = provider.get_schema()
    assert schema2 is schema1
    assert client.get_active_revision_schema.call_count == 1

    # When revisionId changes:
    client.get_status.return_value = {
        "status": "Approved",
        "revisionId": "rev-102",
    }
    client.get_active_revision_schema.return_value = {
        "semanticLayerId": "layer-001",
        "revisionId": "rev-102",
        "status": "Approved",
        "schema": {
            "database": "ERP_DB",
            "tables": {
                "transactions": {"columns": [{"name": "tx_id", "type": "int"}]}
            },
        },
    }

    schema3 = provider.get_schema()
    assert provider.cached_revision_id == "rev-102"
    assert "transactions" in schema3.get("tables", {})
    assert client.get_active_revision_schema.call_count == 2


def test_schema_provider_falls_back_to_file_when_endpoint_fails():
    client = MagicMock()
    client.get_active_revision_schema.side_effect = RuntimeError("404 Not Found")
    client.get_status.return_value = {
        "status": "Approved",
        "sources": {"schemaFileId": "file-schema-fallback"},
    }
    client._get.return_value = {
        "content": {
            "database": "ERP_DB",
            "tables": {
                "cards": {"columns": [{"name": "card_id", "type": "int"}]}
            },
        },
    }

    provider = BackendDatabaseSchemaProvider(client=client)
    schema = provider.get_schema()
    assert provider.cached_schema_file_id == "file-schema-fallback"
    assert "cards" in schema.get("tables", {})
    assert client.get_status.call_count == 1

