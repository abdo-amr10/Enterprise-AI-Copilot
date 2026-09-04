"""Build request-level audit summaries calculating leaf-stage durations and unaccounted time."""
from __future__ import annotations

from typing import Any
from src.observability.audit_context import RequestAuditContext


def build_request_summary(ctx: RequestAuditContext) -> dict[str, Any]:
    """Compile the final request summary event from a completed RequestAuditContext."""
    total_ms = ctx.total_duration_ms or 0.0

    # Calculate sum of leaf-stage durations for backward compatibility
    leaf_durations = {k: round(v, 2) for k, v in ctx.leaf_stage_durations_ms.items()}
    sum_leaf_ms = round(sum(leaf_durations.values()), 2)
    unaccounted_ms = max(0.0, round(total_ms - sum_leaf_ms, 2))
    unaccounted_pct = round((unaccounted_ms / total_ms * 100.0), 1) if total_ms > 0 else 0.0

    # Calculate stage percentages of total latency
    stage_percentages = {
        k: round((v / total_ms * 100.0), 1) if total_ms > 0 else 0.0
        for k, v in leaf_durations.items()
    }

    # Pipeline vs API Framework Overhead
    pipeline_span = next(
        (s for s in ctx.all_spans if s.name == "pipeline"),
        None,
    )
    if pipeline_span is not None:
        pipeline_ms = round(pipeline_span.inclusive_duration_ms, 2)
        api_overhead_ms = max(0.0, round(total_ms - pipeline_ms, 2))
    elif ctx.pipeline_duration_ms is not None:
        pipeline_ms = round(ctx.pipeline_duration_ms, 2)
        api_overhead_ms = max(0.0, round(total_ms - pipeline_ms, 2))
    else:
        pipeline_ms = round(total_ms, 2)
        api_overhead_ms = 0.0

    root_dict = ctx.root_span.to_dict() if ctx.root_span else {}

    summary = {
        "event": "request_summary",
        "request_id": ctx.request_id,
        "correlation_id": ctx.correlation_id,
        "traceparent": ctx.traceparent,
        "success": ctx.success,
        "error_type": ctx.error_type,
        "final_stage": ctx.final_stage,
        "total_duration_ms": round(total_ms, 2),
        "pipeline_duration_ms": pipeline_ms,
        "api_framework_overhead_ms": api_overhead_ms,
        "sum_of_leaf_stages_ms": sum_leaf_ms,
        "unaccounted_ms": unaccounted_ms,
        "unaccounted_percentage": unaccounted_pct,
        "leaf_stages_ms": leaf_durations,
        "leaf_stages_percentage": stage_percentages,
        "counts": dict(ctx.counts),
        "duplicate_work_detected": bool(
            ctx.counts.get("duplicate_prompts", 0) > 0
            or ctx.counts.get("duplicate_sql", 0) > 0
            or ctx.counts.get("duplicate_backend_calls", 0) > 0
        ),
        "hierarchy": root_dict,
        "child_covered_ms": round(ctx.root_span.child_covered_duration_ms, 2) if ctx.root_span else sum_leaf_ms,
        "orchestration_gaps_ms": round(ctx.root_span.orchestration_gaps_ms, 2) if ctx.root_span else 0.0,
        "exclusive_duration_ms": round(ctx.root_span.exclusive_duration_ms, 2) if ctx.root_span else 0.0,
    }

    # Include system resource delta if available
    start_sys = ctx.metadata.get("start_system_snapshot")
    end_sys = ctx.metadata.get("end_system_snapshot")
    if start_sys and end_sys:
        summary["system_delta"] = {
            "cpu_percent_start": start_sys.get("cpu_percent"),
            "cpu_percent_end": end_sys.get("cpu_percent"),
            "ram_used_mb_start": start_sys.get("ram_used_mb"),
            "ram_used_mb_end": end_sys.get("ram_used_mb"),
            "process_rss_mb_start": start_sys.get("process_rss_mb"),
            "process_rss_mb_end": end_sys.get("process_rss_mb"),
        }

    return summary
