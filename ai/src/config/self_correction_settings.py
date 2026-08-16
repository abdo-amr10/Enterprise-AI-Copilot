"""Runtime configuration for the Self-Correction loop.

Configuration is intentionally kept outside application business logic,
matching the existing SemanticSettings pattern.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SelfCorrectionSettings:
    max_attempts: int = 3
