"""Physical schema adapter backed by the active Backend semantic layer."""

from __future__ import annotations

from typing import Any

from src.infrastructure.backend.backend_semantic_client import BackendSemanticClient
from src.infrastructure.semantic_layer.ingestion.schema_loader import SchemaLoader


class BackendDatabaseSchemaProvider:
    def __init__(self, client: BackendSemanticClient | None = None) -> None:
        self._client = client or BackendSemanticClient()

    def get_schema(self) -> dict[str, Any]:
        status = self._client.get_status()
        sources = status.get("sources")
        if not isinstance(sources, dict):
            raise RuntimeError("Backend status did not provide the active schema file ID.")
        schema_file_id = sources.get("schema") or sources.get("schemaFileId")
        if not isinstance(schema_file_id, str) or not schema_file_id:
            raise RuntimeError("Backend status did not provide the active schema file ID.")
        payload = self._client._get(f"/api/v1/semantic-layer/files/{schema_file_id}")
        content = payload.get("content")
        if not isinstance(content, dict):
            raise RuntimeError("Backend schema source must be JSON.")
        return SchemaLoader().load(content)
