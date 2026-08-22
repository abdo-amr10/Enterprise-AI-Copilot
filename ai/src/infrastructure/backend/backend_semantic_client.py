"""Configuration-driven client for Backend-owned semantic source material."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BackendSemanticClient:
    """Fetches source files and revisions; it never treats local artifacts as authoritative."""

    def __init__(self) -> None:
        self._base_url = os.environ.get("BACKEND_API_BASE_URL", "").rstrip("/")
        self._token = os.environ.get("BACKEND_SERVICE_BEARER_TOKEN", "")
        self._timeout = float(os.environ.get("BACKEND_API_TIMEOUT_SECONDS", "30"))
        if not self._base_url:
            raise RuntimeError("BACKEND_API_BASE_URL must be configured for semantic runtime requests.")
        if not self._token:
            raise RuntimeError("BACKEND_SERVICE_BEARER_TOKEN must be configured for semantic runtime requests.")

    def load_generation_sources(self, source_file_ids: dict[str, str]) -> dict[str, Any]:
        sources: dict[str, Any] = {}
        for name, file_id in source_file_ids.items():
            if file_id:
                payload = self._get(f"/api/v1/semantic-layer/files/{file_id}")
                sources[name] = payload.get("content")
        schema = sources.get("schema")
        if not isinstance(schema, dict):
            raise ValueError("The Backend schema source must be a JSON object.")
        sources["relationships"] = sources.get("relationships") or schema.get("relationships", [])
        if not isinstance(sources["relationships"], list):
            raise ValueError("The Backend schema relationships must be a list.")
        return sources

    def load_revision(self, revision_id: str) -> dict[str, Any]:
        payload = self._get(f"/api/v1/semantic-layer/revisions/{revision_id}")
        content = payload.get("content")
        if not isinstance(content, dict):
            raise ValueError("The Backend revision has no semantic content.")
        return content

    def get_status(self) -> dict[str, Any]:
        return self._get("/api/v1/semantic-layer/status")

    def _get(self, path: str) -> dict[str, Any]:
        request = Request(f"{self._base_url}{path}", headers={"Authorization": f"Bearer {self._token}"})
        try:
            with urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise RuntimeError(f"Backend semantic request failed with HTTP {error.code}.") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RuntimeError("Backend semantic request failed.") from error
        if not isinstance(payload, dict):
            raise RuntimeError("Backend semantic response must be an object.")
        return payload
