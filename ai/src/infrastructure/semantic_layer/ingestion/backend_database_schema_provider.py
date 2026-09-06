"""Physical schema adapter backed by the active Backend semantic layer."""

from __future__ import annotations

import threading
from typing import Any

from src.infrastructure.backend.backend_semantic_client import BackendSemanticClient
from src.infrastructure.semantic_layer.ingestion.schema_loader import SchemaLoader


class BackendDatabaseSchemaProvider:
    """Provides the active physical schema with version-bound in-memory caching."""

    def __init__(self, client: BackendSemanticClient | None = None) -> None:
        self._client = client or BackendSemanticClient()
        self._lock = threading.RLock()
        self._cached_revision_id: str | None = None
        self._cached_schema_file_id: str | None = None
        self._cached_schema: dict[str, Any] | None = None

    @property
    def cached_schema_file_id(self) -> str | None:
        """Return the schema file ID currently cached in memory."""
        return self._cached_schema_file_id

    @property
    def cached_revision_id(self) -> str | None:
        """Return the revision ID currently cached in memory."""
        return self._cached_revision_id

    def get_schema(self, allow_cold_start: bool = True) -> dict[str, Any]:
        """Return the physical database schema from in-memory cache with zero Backend HTTP requests on hot path."""
        if self._cached_schema is not None:
            return self._cached_schema

        with self._lock:
            if self._cached_schema is not None:
                return self._cached_schema
            if not allow_cold_start:
                raise RuntimeError(
                    "SchemaNotReady: Physical database schema is not loaded in memory. "
                    "Cold load must not run during a user request; "
                    "ensure warmup has completed or trigger schema synchronization."
                )
            return self.sync_schema()

    def sync_schema(self) -> dict[str, Any]:
        """Warm up or synchronize the in-memory schema with the active Backend version."""
        with self._lock:
            # 1. Primary Strategy: Try direct active revision schema endpoint
            try:
                payload = self._client.get_active_revision_schema()
                revision_id = payload.get("revisionId") or payload.get("revision_id")
                schema_content = payload.get("schema")
                if isinstance(schema_content, dict) and schema_content:
                    parsed = SchemaLoader().load(schema_content)
                    self._cached_revision_id = revision_id
                    self._cached_schema = parsed
                    return parsed
            except Exception:
                # Fall back to status / file lookup only if primary endpoint fails or during legacy sync
                pass

            # 2. Fallback Strategy: Look up schema file via status sources
            try:
                status = self._client.get_status()
                active_revision_id = status.get("revisionId") or status.get("revision_id")
                sources = status.get("sources") if isinstance(status.get("sources"), dict) else {}
                schema_file_id = sources.get("schema") or sources.get("schemaFileId")
                if isinstance(schema_file_id, str) and schema_file_id:
                    payload = self._client._get(f"/api/v1/semantic-layer/files/{schema_file_id}")
                    content = payload.get("content")
                    if isinstance(content, dict):
                        parsed = SchemaLoader().load(content)
                        self._cached_schema_file_id = schema_file_id
                        self._cached_revision_id = active_revision_id
                        self._cached_schema = parsed
                        return parsed
            except Exception:
                pass

            if self._cached_schema is not None:
                return self._cached_schema
            raise RuntimeError("Backend status did not provide the active schema file ID.")

    def invalidate(self) -> None:
        """Clear the in-memory schema cache."""
        with self._lock:
            self._cached_schema = None
            self._cached_schema_file_id = None
            self._cached_revision_id = None

