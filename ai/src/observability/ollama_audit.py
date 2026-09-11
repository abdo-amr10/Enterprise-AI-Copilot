"""Extract, parse, and analyze native Ollama engine metrics and truncation status."""
from __future__ import annotations

from typing import Any


def parse_ollama_metrics(
    raw_response: Any,
    *,
    context_length: int = 4096,
    max_output_tokens: int = 2048,
    estimated_prompt_tokens: int | None = None,
    client_duration_ms: float | None = None,
) -> dict[str, Any]:
    """Extract granular timing, throughput, and truncation diagnostics from an Ollama response.

    Fails open: returns safe defaults if metrics are missing.
    """
    metrics: dict[str, Any] = {}

    def _get(attr: str) -> Any:
        if isinstance(raw_response, dict):
            return raw_response.get(attr)
        return getattr(raw_response, attr, None)

    total_ns = _get("total_duration")
    load_ns = _get("load_duration")
    prompt_eval_ns = _get("prompt_eval_duration")
    prompt_eval_count = _get("prompt_eval_count")
    eval_ns = _get("eval_duration")
    eval_count = _get("eval_count")
    done_reason = _get("done_reason")

    total_ms = float(total_ns) / 1_000_000.0 if total_ns is not None else client_duration_ms
    load_ms = float(load_ns) / 1_000_000.0 if load_ns is not None else 0.0
    prompt_eval_ms = float(prompt_eval_ns) / 1_000_000.0 if prompt_eval_ns is not None else 0.0
    eval_ms = float(eval_ns) / 1_000_000.0 if eval_ns is not None else 0.0
    server_eval_ms = prompt_eval_ms + eval_ms

    client_overhead_ms = (
        max(0.0, client_duration_ms - (server_eval_ms + load_ms))
        if client_duration_ms is not None
        else 0.0
    )

    metrics["total_duration_ms"] = round(total_ms, 2) if total_ms is not None else None
    metrics["load_duration_ms"] = round(load_ms, 2)
    metrics["prompt_eval_duration_ms"] = round(prompt_eval_ms, 2)
    metrics["eval_duration_ms"] = round(eval_ms, 2)
    metrics["server_duration_ms"] = round(server_eval_ms, 2)
    metrics["client_duration_ms"] = round(client_duration_ms, 2) if client_duration_ms is not None else None
    metrics["client_overhead_ms"] = round(client_overhead_ms, 2)
    metrics["prompt_eval_count"] = int(prompt_eval_count) if prompt_eval_count is not None else None
    metrics["eval_count"] = int(eval_count) if eval_count is not None else None
    metrics["done_reason"] = str(done_reason) if done_reason else None

    # Factual model loading evidence
    if load_ns is None:
        metrics["model_load_type"] = "none"
        metrics["cold_load"] = None
        metrics["is_cold_load"] = False
    elif load_ms == 0.0:
        metrics["model_load_type"] = "warm"
        metrics["cold_load"] = False
        metrics["is_cold_load"] = False
    else:
        metrics["model_load_type"] = "cold"
        metrics["cold_load"] = True
        metrics["is_cold_load"] = True

    # Throughput calculations (TPS)
    if prompt_eval_count is not None and prompt_eval_ms > 0:
        metrics["prompt_tps"] = round((prompt_eval_count / (prompt_eval_ms / 1000.0)), 2)
    else:
        metrics["prompt_tps"] = None

    if eval_count is not None and eval_ms > 0:
        metrics["generation_tps"] = round((eval_count / (eval_ms / 1000.0)), 2)
    else:
        metrics["generation_tps"] = None

    # Percentages of total engine duration
    if total_ms and total_ms > 0:
        metrics["load_percentage"] = round((load_ms / total_ms) * 100.0, 1)
        metrics["prompt_eval_percentage"] = round((prompt_eval_ms / total_ms) * 100.0, 1)
        metrics["generation_percentage"] = round((eval_ms / total_ms) * 100.0, 1)
    else:
        metrics["load_percentage"] = 0.0
        metrics["prompt_eval_percentage"] = 0.0
        metrics["generation_percentage"] = 0.0

    # Truncation Detection
    # Ollama llama-server slot budget rule: max input = num_ctx - num_predict + 2
    available_input_budget = max(0, context_length - max_output_tokens + 2)
    metrics["context_length"] = context_length
    metrics["max_output_tokens"] = max_output_tokens
    metrics["available_input_budget"] = available_input_budget

    if prompt_eval_count is not None:
        if (
            estimated_prompt_tokens is not None
            and estimated_prompt_tokens > available_input_budget
            and abs(prompt_eval_count - available_input_budget) <= 10
        ):
            metrics["prompt_truncated"] = True
            metrics["truncated_tokens_estimate"] = estimated_prompt_tokens - prompt_eval_count
        elif estimated_prompt_tokens is not None and estimated_prompt_tokens <= available_input_budget:
            metrics["prompt_truncated"] = False
            metrics["truncated_tokens_estimate"] = 0
        else:
            # If prompt_eval_count hit the exact available limit
            metrics["prompt_truncated"] = bool(prompt_eval_count >= available_input_budget - 2)
            metrics["truncated_tokens_estimate"] = (
                max(0, (estimated_prompt_tokens or prompt_eval_count) - available_input_budget)
                if metrics["prompt_truncated"]
                else 0
            )
    else:
        metrics["prompt_truncated"] = None
        metrics["truncated_tokens_estimate"] = None

    return metrics
