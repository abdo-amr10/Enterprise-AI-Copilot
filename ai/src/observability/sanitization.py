"""Allowlisted serialization and redaction for observability events.

Ensures raw prompts, customer questions, generated SQL, credentials, and internal
exception traces never leave the runtime process unredacted.
"""
from __future__ import annotations

import hashlib
from typing import Any

SENSITIVE_KEYS = {
    "question", "prompt", "sql", "text", "semantic_context", "raw_response",
    "model_response", "exception", "message", "content", "credentials",
    "credential", "password", "token", "bearer_token", "authorization",
    "user_id", "branch_id",
}


def stable_hash(value: str) -> str:
    """Compute a deterministic SHA-256 hex digest for a string value.

    Args:
        value: Input string to hash.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_error(error: BaseException) -> str:
    """Extract a sanitized error representation without exposing sensitive details.

    Args:
        error: Caught exception instance.

    Returns:
        The exception type class name (e.g. 'ValueError', 'HTTPError').
    """
    return type(error).__name__


def safe_event(event: dict[str, Any]) -> dict[str, Any]:
    """Sanitize an observability event dictionary by redacting sensitive fields.

    Sensitive keys (prompts, questions, credentials, raw SQL) are replaced with
    their SHA-256 hash and string length. Collections are replaced with their element count.

    Args:
        event: Raw event metadata dictionary.

    Returns:
        A sanitized dictionary safe for external telemetry emission.
    """
    result: dict[str, Any] = {}
    for key, value in event.items():
        normalized = str(key)
        if normalized in SENSITIVE_KEYS or normalized.lower().endswith("sql"):
            if isinstance(value, str):
                result[f"{normalized}_hash"] = stable_hash(value)
                result[f"{normalized}_length"] = len(value)
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[normalized] = value
        elif isinstance(value, (list, tuple)):
            result[f"{normalized}_count"] = len(value)
    return result
