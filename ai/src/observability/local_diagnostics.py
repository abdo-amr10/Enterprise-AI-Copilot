"""Local-only diagnostics for failures retained as exception causes by runtime clients."""
from __future__ import annotations

import re
import socket
import ssl
from typing import Any
from urllib.error import HTTPError, URLError

_SECRET = re.compile(r"(?i)(bearer\s+|authorization\s*[:=]\s*|token\s*[:=]\s*|password\s*[:=]\s*)[^\s,;]+")
_JWT = re.compile(r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b")


def _redact(value: str | None) -> str:
    text = value or ""
    text = _JWT.sub("[redacted-jwt]", _SECRET.sub(r"\1[redacted]", text))
    return text[:500] if text else "unavailable"


def _chain(error: BaseException) -> list[BaseException]:
    values, current = [], error
    while current is not None and current not in values:
        values.append(current)
        current = current.__cause__ or current.__context__
    return values


def backend_request_diagnostic(error: BaseException, *, method: str = "GET", path: str = "/api/v1/semantic-layer/status") -> dict[str, Any]:
    """Return a deliberately small, local-only diagnostic without headers or secrets."""
    result: dict[str, Any] = {"exception_type": type(error).__name__, "method": method, "path": path, "http_status": "unavailable", "category": "unknown", "response_message": "unavailable", "response_body": "unavailable"}
    for item in _chain(error):
        if isinstance(item, HTTPError):
            body = ""
            try:
                body = item.read().decode("utf-8", errors="replace") if getattr(item, "fp", None) else ""
            except Exception:
                body = ""
            # Error bodies can contain semantic/source content; expose only presence and size locally.
            result.update(http_status=item.code, response_message=_redact(getattr(item, "reason", None)), response_body=f"redacted_response_body_bytes={len(body.encode('utf-8'))}" if body else "unavailable")
            result["category"] = "authentication_authorization" if item.code in {401, 403} else "endpoint_not_found" if item.code == 404 else "server_error" if 500 <= item.code < 600 else "unknown"
            return result
        if isinstance(item, (TimeoutError, socket.timeout)):
            result.update(exception_type=type(item).__name__, category="timeout", response_message=_redact(str(item)))
            return result
        if isinstance(item, ssl.SSLError):
            result.update(exception_type=type(item).__name__, category="tls_certificate_failure", response_message=_redact(str(item)))
            return result
        if isinstance(item, URLError):
            reason = item.reason
            if isinstance(reason, (TimeoutError, socket.timeout)):
                result.update(exception_type=type(reason).__name__, category="timeout", response_message=_redact(str(reason)))
            elif isinstance(reason, ssl.SSLError) or "CERTIFICATE" in str(reason).upper() or "SSL" in str(reason).upper():
                result.update(exception_type=type(reason).__name__, category="tls_certificate_failure", response_message=_redact(str(reason)))
            else:
                result.update(exception_type=type(reason).__name__, category="connection_failure", response_message=_redact(str(reason)))
            return result
        if isinstance(item, ConnectionError):
            result.update(exception_type=type(item).__name__, category="connection_failure", response_message=_redact(str(item)))
            return result
    return result
