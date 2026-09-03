"""Physical schema adapter backed by the active Backend semantic layer."""

from __future__ import annotations

from typing import Any

from src.infrastructure.backend.backend_semantic_client import BackendSemanticClient
from src.infrastructure.semantic_layer.ingestion.schema_loader import SchemaLoader


class BackendDatabaseSchemaProvider:
    """Provides the active physical schema with version-bound in-memory caching."""

    def __init__(self, client: BackendSemanticClient | None = None) -> None:
        self._client = client or BackendSemanticClient()
        self._cached_schema_file_id: str | None = None
        self._cached_schema: dict[str, Any] | None = None

    @property
    def cached_schema_file_id(self) -> str | None:
        """Return the schema file ID currently cached in memory."""
        return self._cached_schema_file_id

    def get_schema(self) -> dict[str, Any]:
        """Return the physical database schema, caching in RAM by schemaFileId."""
        status = self._client.get_status()
        sources = status.get("sources")
        if not isinstance(sources, dict):
            raise RuntimeError("Backend status did not provide the active schema file ID.")
        schema_file_id = sources.get("schema") or sources.get("schemaFileId")
        if not isinstance(schema_file_id, str) or not schema_file_id:
            raise RuntimeError("Backend status did not provide the active schema file ID.")

        if self._cached_schema is not None and self._cached_schema_file_id == schema_file_id:
            return self._cached_schema

        payload = self._client._get(f"/api/v1/semantic-layer/files/{schema_file_id}")
        content = payload.get("content")
        if not isinstance(content, dict):
            raise RuntimeError("Backend schema source must be JSON.")
        parsed = SchemaLoader().load(content)
        self._cached_schema_file_id = schema_file_id
        self._cached_schema = parsed
        return parsed

    def sync_schema(self) -> dict[str, Any]:
        """Warm up or synchronize the in-memory schema with the active Backend version."""
        return self.get_schema()

    def invalidate(self) -> None:
        """Clear the in-memory schema cache."""
        self._cached_schema = None
        self._cached_schema_file_id = None

