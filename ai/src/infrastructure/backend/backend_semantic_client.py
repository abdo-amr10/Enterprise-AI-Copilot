"""Configuration-driven client for Backend-owned semantic source material."""

from __future__ import annotations

import json
import os
import ssl
from typing import Any
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BackendSemanticClient:
    """Fetches source files and revisions; it never treats local artifacts as authoritative."""

    def __init__(self) -> None:
        self._base_url = os.environ.get("BACKEND_API_BASE_URL", "").rstrip("/")
        self._token = os.environ.get("BACKEND_SERVICE_BEARER_TOKEN", "")
        self._timeout = float(os.environ.get("BACKEND_API_TIMEOUT_SECONDS", "30"))
        self._allow_insecure_local_https = (
            os.environ.get("BACKEND_ALLOW_INSECURE_LOCAL_HTTPS", "").casefold()
            == "true"
        )
        if not self._base_url:
            raise RuntimeError("BACKEND_API_BASE_URL must be configured for semantic runtime requests.")
        if not self._token:
            raise RuntimeError("BACKEND_SERVICE_BEARER_TOKEN must be configured for semantic runtime requests.")

    def load_generation_sources(self, source_file_ids: dict[str, str]) -> dict[str, Any]:
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

        if name == "glossary":
            return "business_glossary"
        if name == "sampleData":
            return "sample_data"
        return name

    def load_revision(self, revision_id: str) -> dict[str, Any]:
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
        self._normalize_relationship_tables(result)
        return result

    @staticmethod
    def _normalize_relationship_tables(layer: dict[str, Any]) -> None:
        """Translate entity-based Backend relationships to physical tables.

        The Semantic Layer stores relationships using ``from_entity`` and
        ``to_entity``. SQL validation and context assembly operate on physical
        table names, so enrich the runtime copy without changing persistence.
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
            if not relationship.get("from_table"):
                relationship["from_table"] = entity_tables.get(
                    relationship.get("from_entity")
                )
            if not relationship.get("to_table"):
                relationship["to_table"] = entity_tables.get(
                    relationship.get("to_entity")
                )

    def get_status(self) -> dict[str, Any]:
        return self._get("/api/v1/semantic-layer/status")

    def _get(self, path: str) -> dict[str, Any]:
        request = Request(f"{self._base_url}{path}", headers={"Authorization": f"Bearer {self._token}"})
        try:
            with urlopen(
                request,
                timeout=self._timeout,
                context=self._ssl_context(),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise RuntimeError(f"Backend semantic request failed with HTTP {error.code}.") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RuntimeError("Backend semantic request failed.") from error
        if not isinstance(payload, dict):
            raise RuntimeError("Backend semantic response must be an object.")
        return payload

    def _ssl_context(self) -> ssl.SSLContext | None:
        """Allow an untrusted development certificate only for local HTTPS."""

        parsed = urlparse(self._base_url)
        is_local_https = (
            parsed.scheme == "https"
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        )
        if self._allow_insecure_local_https and is_local_https:
            return ssl._create_unverified_context()
        return None
