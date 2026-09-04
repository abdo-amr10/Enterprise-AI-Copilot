from __future__ import annotations

import os
import time
from typing import Any

import requests

from src.infrastructure.backend.backend_http_client import BackendHttpClient


class BackendSemanticClient:
    """HTTP client communicating with the Backend API for semantic layer assets.

    Fetches authoritative uploaded source files (schema, relationships, glossary, documentation)
    and revision artifacts from the Backend API over authenticated HTTPS/HTTP.
    """

    def __init__(self, http_client: BackendHttpClient | None = None) -> None:
        """Initialize the Backend semantic client from environment variables or shared client.

        Raises:
            RuntimeError: If BACKEND_API_BASE_URL is unset, or if neither BACKEND_SERVICE_BEARER_TOKEN
                nor (BACKEND_SERVICE_EMAIL and BACKEND_SERVICE_PASSWORD) is configured.
        """
        self._cached_status: dict[str, Any] | None = None
        self._cached_status_time: float = 0.0
        self._status_cache_ttl: float = float(
            os.environ.get("BACKEND_STATUS_CACHE_TTL_SECONDS", "3.0")
        )
        if http_client is not None:
            self._http_client = http_client
            self._base_url = http_client._base_url
            self._token = http_client._token
            self._timeout = float(http_client._timeout)
            return

        self._base_url = os.environ.get("BACKEND_API_BASE_URL", "").rstrip("/")
        self._token = os.environ.get("BACKEND_SERVICE_BEARER_TOKEN", "")
        self._email = os.environ.get("BACKEND_SERVICE_EMAIL", "")
        self._password = os.environ.get("BACKEND_SERVICE_PASSWORD", "")
        self._timeout = float(os.environ.get("BACKEND_API_TIMEOUT_SECONDS", "30"))
        self._allow_insecure_local_https = (
            os.environ.get("BACKEND_ALLOW_INSECURE_LOCAL_HTTPS", "").casefold()
            == "true"
        )
        if not self._base_url:
            raise RuntimeError("BACKEND_API_BASE_URL must be configured for semantic runtime requests.")
        if not self._token and not (self._email and self._password):
            raise RuntimeError(
                "Either BACKEND_SERVICE_BEARER_TOKEN or (BACKEND_SERVICE_EMAIL and BACKEND_SERVICE_PASSWORD) "
                "must be configured for semantic runtime requests."
            )

        self._http_client = BackendHttpClient(
            base_url=self._base_url,
            token=self._token,
            email=self._email,
            password=self._password,
            timeout=int(self._timeout),
            verify_tls=not self._allow_insecure_local_https,
        )

    def load_generation_sources(self, source_file_ids: dict[str, str]) -> dict[str, Any]:
        """Fetch and normalize uploaded source files required for draft generation.

        Args:
            source_file_ids: Mapping of source category names to Backend file IDs.

        Returns:
            Dictionary containing normalized sources (schema, relationships, business_glossary, etc.).

        Raises:
            ValueError: If schema content is missing or malformed.
        """
        sources: dict[str, Any] = {}
        for name, file_id in source_file_ids.items():
            if file_id:
                payload = self._get(f"/api/v1/semantic-layer/files/{file_id}")
                sources[self._source_key(name)] = payload.get("content")
        schema = sources.get("schema")
        if not isinstance(schema, dict):
            raise ValueError("The Backend schema source must be a JSON object.")
        sources["relationships"] = sources.get("relationships") or schema.get("relationships", [])
        if not isinstance(sources["relationships"], list):
            raise ValueError("The Backend schema relationships must be a list.")
        return sources

    @staticmethod
    def _source_key(name: str) -> str:
        """Normalize Backend source names to the AI build-input vocabulary."""
        key = name.lower()
        if key in ("glossary", "businessglossary", "business_glossary"):
            return "business_glossary"
        if key in ("sampledata", "sample_data"):
            return "sample_data"
        if key in ("documentation", "docs", "doc"):
            return "documentation"
        if key in ("schema", "database_schema"):
            return "schema"
        if key in ("relationships", "relationship"):
            return "relationships"
        return name

    def load_revision(self, revision_id: str) -> dict[str, Any]:
        """Fetch an authoritative semantic layer revision from the Backend by ID.

        Args:
            revision_id: Unique revision UUID.

        Returns:
            Semantic layer dictionary with restored metadata.

        Raises:
            ValueError: If revision content is missing or malformed.
        """
        payload = self._get(f"/api/v1/semantic-layer/revisions/{revision_id}")
        content = payload.get("content")
        if not isinstance(content, dict):
            raise ValueError("The Backend revision has no semantic content.")

        # The Backend's revision DTO exposes the revision identity alongside
        # ``content`` but does not include the draft metadata persisted by AI.
        # Retrieval requires that lineage, so restore it from the authoritative
        # outer response without fabricating any IDs.
        result = dict(content)
        metadata = result.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        metadata.setdefault("semantic_layer_id", payload.get("semanticLayerId"))
        metadata.setdefault("revision_id", payload.get("revisionId"))
        # ``status`` belongs to the Backend revision envelope rather than its
        # content.  Preserve it in the in-memory retrieval copy so the
        # approved-only embedding/indexing pipeline can enforce the same
        # lifecycle boundary as the Backend.
        status = payload.get("status")
        if isinstance(status, str):
            metadata.setdefault("status", status.casefold())
        result["metadata"] = metadata

        # Backend JSON uses camelCase, while the AI domain model uses these
        # snake_case section names internally.
        result.setdefault("business_rules", result.pop("businessRules", []))
        result.setdefault("validation_issues", result.pop("validationIssues", []))
        result.setdefault("security_domains", result.pop("securityDomains", []))
        self._normalize_relationships(result)
        return result

    @staticmethod
    def _normalize_relationships(layer: dict[str, Any]) -> None:
        """Normalize supported Backend relationship key styles for AI consumers.

        The persisted JSON is backend-owned and may use either camelCase or
        snake_case field names. Convert known aliases into the AI's canonical
        names, then resolve entity names to physical tables where possible.
        Missing join columns are deliberately not guessed: downstream context
        code excludes incomplete relationships rather than fabricating a JOIN.
        """

        entity_tables = {
            entity.get("name"): entity.get("mapping") or entity.get("table")
            for entity in layer.get("entities", [])
            if isinstance(entity, dict)
            and isinstance(entity.get("name"), str)
            and isinstance(entity.get("mapping") or entity.get("table"), str)
        }
        for relationship in layer.get("relationships", []):
            if not isinstance(relationship, dict):
                continue
            for canonical, aliases in {
                "from_table": ("fromTable", "source_table", "sourceTable"),
                "to_table": ("toTable", "target_table", "targetTable"),
                "from_column": (
                    "fromColumn", "from_field", "fromField", "from_attribute",
                    "fromAttribute", "source_column", "sourceColumn",
                ),
                "to_column": (
                    "toColumn", "to_field", "toField", "to_attribute",
                    "toAttribute", "target_column", "targetColumn",
                ),
                "from_entity": ("fromEntity", "source_entity", "sourceEntity"),
                "to_entity": ("toEntity", "target_entity", "targetEntity"),
            }.items():
                if relationship.get(canonical) is None:
                    value = next(
                        (relationship[key] for key in aliases if relationship.get(key) is not None),
                        None,
                    )
                    if value is not None:
                        relationship[canonical] = value
            if not relationship.get("from_table"):
                relationship["from_table"] = entity_tables.get(
                    relationship.get("from_entity")
                )
            if not relationship.get("to_table"):
                relationship["to_table"] = entity_tables.get(
                    relationship.get("to_entity")
                )

    def get_active_revision_schema(self) -> dict[str, Any]:
        """Fetch the physical database schema for the active revision from the Backend API.

        Calls GET /api/v1/semantic-layer/revisions/active/schema.

        Returns:
            Dictionary containing:
                - semanticLayerId: UUID string
                - revisionId: UUID string
                - status: string (e.g. "Approved")
                - schema: dict representing the physical database schema
        """
        payload = self._get("/api/v1/semantic-layer/revisions/active/schema")
        if not isinstance(payload, dict):
            raise ValueError("Backend active revision schema response must be a JSON object.")
        return payload

    def get_status(self, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if (
            not force
            and self._cached_status is not None
            and (now - self._cached_status_time) < self._status_cache_ttl
        ):
            return self._cached_status

        status = self._get("/api/v1/semantic-layer/status")
        self._cached_status = status
        self._cached_status_time = now
        return status

    def _get(self, path: str) -> dict[str, Any]:
        try:
            return self._http_client.get(path)
        except requests.HTTPError as error:
            status_code = error.response.status_code if error.response is not None else "unknown"
            detail = ""
            if error.response is not None:
                try:
                    detail = error.response.text.strip()
                except Exception:
                    pass
            suffix = f" Details: {detail[:500]}" if detail else ""
            raise RuntimeError(
                f"Backend semantic request failed with HTTP {status_code}.{suffix}"
            ) from error
        except (requests.RequestException, ValueError) as error:
            raise RuntimeError("Backend semantic request failed.") from error
