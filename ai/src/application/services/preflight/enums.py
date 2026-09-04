"""Action outcomes produced by deterministic preflight validation."""

from enum import Enum


class PreflightAction(str, Enum):
    """Action outcome from a deterministic preflight gate."""

    PASS = "pass"
    SKIP = "skip"
    BLOCK = "block"
