"""Result model for preflight validation checks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from src.application.services.preflight.enums import PreflightAction


@dataclass(frozen=True)
class PreflightResult:
    """Immutable result contract from deterministic preflight checks."""

    action: PreflightAction
    code: str
    message: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
