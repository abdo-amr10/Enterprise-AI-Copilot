"""Environment-only configuration for the developer observability and tracing subsystem.

Controls MLflow tracking, sampling rates, latency thresholds, and safe offline
defaults without impacting the production AI runtime.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: bool = False) -> bool:
    """Parse an environment variable as a boolean flag.

    Args:
        name: Name of the environment variable.
        default: Fallback boolean value if the variable is not set.

    Returns:
        True if the variable value is '1', 'true', 'yes', or 'on' (case-insensitive);
        otherwise False.
    """
    return os.getenv(name, str(default)).strip().casefold() in {"1", "true", "yes", "on"}


def _number(name: str, default: float) -> float:
    """Parse an environment variable as a numeric float value.

    Args:
        name: Name of the environment variable.
        default: Fallback float value if the variable is not set.

    Returns:
        The parsed floating-point number.

    Raises:
        ValueError: If the environment variable contains a non-numeric string.
    """
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric.") from exc


@dataclass(frozen=True)
class ObservabilitySettings:
    """Immutable configuration for MLflow observability and tracing.

    Attributes:
        enabled: Master toggle for observability logging. Defaults to False to
            prevent unmocked network hangs during local testing.
        tracking_uri: Target MLflow tracking server URI.
        experiment_name: MLflow experiment name for grouping runs.
        trace_sample_rate: Fraction of successful runs to trace (between 0.0 and 1.0).
        total_latency_threshold_ms: Millisecond latency threshold above which runs
            are automatically captured as slow-request traces.
        retrieval_latency_threshold_ms: Millisecond threshold for slow vector retrieval.
        generation_latency_threshold_ms: Millisecond threshold for slow LLM generation.
        low_retrieval_score: Score threshold below which retrieval quality is flagged.
    """

    enabled: bool = _flag("OBSERVABILITY_ENABLED", default=False)
    tracking_uri: str | None = os.getenv("OBSERVABILITY_TRACKING_URI") or os.getenv("MLFLOW_TRACKING_URI") or "http://127.0.0.1:5000"
    experiment_name: str = os.getenv("OBSERVABILITY_EXPERIMENT_NAME", "enterprise-ai-copilot")
    trace_sample_rate: float = _number("OBSERVABILITY_TRACE_SAMPLE_RATE", 0.0)
    total_latency_threshold_ms: float = _number("OBSERVABILITY_TOTAL_LATENCY_THRESHOLD_MS", 5000)
    retrieval_latency_threshold_ms: float = _number("OBSERVABILITY_RETRIEVAL_LATENCY_THRESHOLD_MS", 1500)
    generation_latency_threshold_ms: float = _number("OBSERVABILITY_LLM_LATENCY_THRESHOLD_MS", 3000)
    low_retrieval_score: float = _number("OBSERVABILITY_LOW_RETRIEVAL_SCORE", -1.0)

    def __post_init__(self) -> None:
        if not 0 <= self.trace_sample_rate <= 1:
            raise ValueError("OBSERVABILITY_TRACE_SAMPLE_RATE must be between 0.0 and 1.0.")
