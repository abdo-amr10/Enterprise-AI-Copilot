"""Decides trace detail after an execution; recording never changes execution."""
from __future__ import annotations
import random
from typing import Any
from src.observability.settings import ObservabilitySettings


def trace_reason(summary: dict[str, Any], settings: ObservabilitySettings, *, developer_debug: bool = False) -> str:
    if developer_debug:
        return "developer_debug"
    if summary.get("status") == "failed": return "error"
    if summary.get("retrieval_result_count") == 0: return "zero_retrieval_results"
    if summary.get("retrieval_min_score") is not None and summary["retrieval_min_score"] < settings.low_retrieval_score: return "low_retrieval_score"
    if summary.get("total_latency_ms", 0) >= settings.total_latency_threshold_ms: return "total_latency_threshold"
    if summary.get("retrieval_latency_ms", 0) >= settings.retrieval_latency_threshold_ms: return "retrieval_latency_threshold"
    if summary.get("generation_latency_ms", 0) >= settings.generation_latency_threshold_ms: return "generation_latency_threshold"
    if settings.trace_sample_rate and random.random() < settings.trace_sample_rate: return "sampled"
    return "metrics_only"
