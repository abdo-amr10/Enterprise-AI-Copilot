"""Allowlisted serialization: raw prompts, questions, SQL and exceptions never leave the process."""
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
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_error(error: BaseException) -> str:
    return type(error).__name__


def safe_event(event: dict[str, Any]) -> dict[str, Any]:
    """Keep only scalar operational facts and replace sensitive values with a hash/length."""
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
