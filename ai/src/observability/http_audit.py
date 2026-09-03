"""Sanitized HTTP audit records for AI -> Backend communications."""
from __future__ import annotations

import re
import urllib.parse
from typing import Any

_QUERY_PARAM_SENSITIVE = re.compile(
    r"(token|auth|key|secret|password|bearer|credential)=[^&]+",
    re.IGNORECASE,
)


def sanitize_url(raw_url: str) -> str:
    """Remove sensitive query parameters and credentials from a URL."""
    if not raw_url:
        return ""
    try:
        parsed = urllib.parse.urlparse(raw_url)
        # Strip userinfo (username:password)
        clean_netloc = parsed.netloc.split("@")[-1] if "@" in parsed.netloc else parsed.netloc
        clean_query = _QUERY_PARAM_SENSITIVE.sub(r"\1=[REDACTED]", parsed.query)
        cleaned = urllib.parse.urlunparse(
            (parsed.scheme, clean_netloc, parsed.path, parsed.params, clean_query, "")
        )
        return cleaned
    except Exception:
        return re.sub(r"[\?&].*$", "", raw_url)


def build_http_audit_event(
    *,
    request_id: str | None,
    stage: str,
    method: str,
    url: str,
    status_code: int | None,
    duration_ms: float,
    request_bytes: int = 0,
    response_bytes: int = 0,
    timeout: float | None = None,
    retry_count: int = 0,
    exception: Exception | None = None,
    is_duplicate: bool = False,
) -> dict[str, Any]:
    """Create a structured, sanitized audit event for an AI -> Backend HTTP call."""
    sanitized = sanitize_url(url)
    endpoint_path = urllib.parse.urlparse(sanitized).path or sanitized

    event = {
        "event": "backend_http_call",
        "request_id": request_id,
        "stage": stage,
        "http_method": method.upper(),
        "endpoint": endpoint_path,
        "url": sanitized,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "request_bytes": request_bytes,
        "response_bytes": response_bytes,
        "timeout_seconds": timeout,
        "retry_count": retry_count,
        "success": bool(status_code is not None and 200 <= status_code < 400 and exception is None),
        "error_type": type(exception).__name__ if exception is not None else None,
        "is_duplicate": is_duplicate,
    }
    return event
