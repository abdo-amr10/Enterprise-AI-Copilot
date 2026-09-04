"""Runtime configuration for deterministic preflight checks.

Configuration is intentionally kept outside application business logic,
matching existing project configuration patterns.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PreflightSettings:
    """Settings governing preflight validation behavior."""

    enabled: bool = os.getenv("PREFLIGHT_ENABLED", "true").casefold() in (
        "true",
        "1",
        "yes",
    )
