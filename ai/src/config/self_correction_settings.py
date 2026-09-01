"""Runtime configuration for the Self-Correction loop.

Configuration is intentionally kept outside application business logic,
matching the existing SemanticSettings pattern.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SelfCorrectionSettings:
    max_attempts: int = int(os.getenv("SELF_CORRECTION_MAX_ATTEMPTS", "3"))
