"""Recursive camelCase <-> snake_case conversion for dict/list JSON trees.

The internal application code (DTOs, services, validator, etc.) is
snake_case throughout. The API spec document is camelCase throughout.
The mock backend below sits exactly where a real Backend controller
would sit, so it is the natural place to do this translation -- the
same way a real controller would map its HTTP JSON body to/from
internal service objects.
"""

from __future__ import annotations

import re
from typing import Any

_SNAKE_RE = re.compile(r"_([a-z0-9])")
_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def snake_to_camel_key(key: str) -> str:
    return _SNAKE_RE.sub(lambda m: m.group(1).upper(), key)


def camel_to_snake_key(key: str) -> str:
    return _CAMEL_RE.sub("_", key).lower()


def to_camel(obj: Any) -> Any:
    """Recursively convert all dict keys from snake_case to camelCase."""

    if isinstance(obj, dict):
        return {
            snake_to_camel_key(k): to_camel(v)
            for k, v in obj.items()
        }

    if isinstance(obj, list):
        return [to_camel(item) for item in obj]

    return obj


def to_snake(obj: Any) -> Any:
    """Recursively convert all dict keys from camelCase to snake_case."""

    if isinstance(obj, dict):
        return {
            camel_to_snake_key(k): to_snake(v)
            for k, v in obj.items()
        }

    if isinstance(obj, list):
        return [to_snake(item) for item in obj]

    return obj
