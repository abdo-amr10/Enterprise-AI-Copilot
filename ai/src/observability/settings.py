"""Environment-only settings for the optional developer observability layer."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().casefold() in {"1", "true", "yes", "on"}


def _number(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric.") from exc


@dataclass(frozen=True)
class ObservabilitySettings:
    enabled: bool = _flag("OBSERVABILITY_ENABLED")
    tracking_uri: str | None = os.getenv("OBSERVABILITY_TRACKING_URI") or os.getenv("MLFLOW_TRACKING_URI")
    experiment_name: str = os.getenv("OBSERVABILITY_EXPERIMENT_NAME", "enterprise-ai-copilot")
    trace_sample_rate: float = _number("OBSERVABILITY_TRACE_SAMPLE_RATE", 0.0)
    total_latency_threshold_ms: float = _number("OBSERVABILITY_TOTAL_LATENCY_THRESHOLD_MS", 5000)
    retrieval_latency_threshold_ms: float = _number("OBSERVABILITY_RETRIEVAL_LATENCY_THRESHOLD_MS", 1500)
    generation_latency_threshold_ms: float = _number("OBSERVABILITY_LLM_LATENCY_THRESHOLD_MS", 3000)
    low_retrieval_score: float = _number("OBSERVABILITY_LOW_RETRIEVAL_SCORE", -1.0)

    def __post_init__(self) -> None:
        if not 0 <= self.trace_sample_rate <= 1:
            raise ValueError("OBSERVABILITY_TRACE_SAMPLE_RATE must be between 0.0 and 1.0.")
