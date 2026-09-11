"""Request-scoped audit context with contextvars propagation and metric tracking."""
from __future__ import annotations

import contextvars
import dataclasses
import time
from typing import Any


@dataclasses.dataclass
class AuditSpan:
    """Represents a hierarchical operation span with monotonic interval timing."""

    span_id: str
    parent_span_id: str | None
    name: str
    stage: str
    operation: str
    start_time_ns: int
    end_time_ns: int | None = None
    inclusive_duration_ms: float = 0.0
    child_covered_duration_ms: float = 0.0
    exclusive_duration_ms: float = 0.0
    orchestration_gaps_ms: float = 0.0
    unaccounted_ms: float = 0.0
    status: str = "ok"  # "ok", "error", "skipped"
    is_leaf: bool = True
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    children: list[AuditSpan] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize span and its children to a nested dictionary."""
        return {
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "stage": self.stage,
            "operation": self.operation,
            "start_time_ns": self.start_time_ns,
            "end_time_ns": self.end_time_ns,
            "inclusive_duration_ms": round(self.inclusive_duration_ms, 3),
            "child_covered_duration_ms": round(self.child_covered_duration_ms, 3),
            "exclusive_duration_ms": round(self.exclusive_duration_ms, 3),
            "orchestration_gaps_ms": round(self.orchestration_gaps_ms, 3),
            "unaccounted_ms": round(self.unaccounted_ms, 3),
            "status": self.status,
            "is_leaf": self.is_leaf,
            "metadata": dict(self.metadata),
            "children": [c.to_dict() for c in self.children],
        }


def compute_interval_union(intervals: list[tuple[int, int]]) -> tuple[int, list[tuple[int, int]]]:
    """Compute total covered duration of a union of intervals, plus disjoint merged intervals.

    Returns:
        (total_covered_ns, merged_disjoint_intervals)
    """
    valid = [(s, e) for s, e in intervals if s is not None and e is not None and e >= s]
    if not valid:
        return 0, []
    valid.sort(key=lambda x: x[0])

    merged: list[tuple[int, int]] = []
    cur_s, cur_e = valid[0]
    for s, e in valid[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            merged.append((cur_s, cur_e))
            cur_s, cur_e = s, e
    merged.append((cur_s, cur_e))

    covered_ns = sum(e - s for s, e in merged)
    return covered_ns, merged


def finalize_span(span: AuditSpan, end_time_ns: int, status: str = "ok") -> None:
    """Finalize an AuditSpan, calculating non-overlapping child coverage, exclusive time, and gaps."""
    span.end_time_ns = end_time_ns
    span.status = status
    total_ns = max(0, end_time_ns - span.start_time_ns)
    span.inclusive_duration_ms = total_ns / 1_000_000.0

    if span.children:
        span.is_leaf = False
        child_intervals = [
            (c.start_time_ns, c.end_time_ns)
            for c in span.children
            if c.end_time_ns is not None
        ]
        covered_ns, merged_intervals = compute_interval_union(child_intervals)
        span.child_covered_duration_ms = covered_ns / 1_000_000.0
        span.exclusive_duration_ms = max(
            0.0, span.inclusive_duration_ms - span.child_covered_duration_ms
        )

        gaps_ns = 0
        if merged_intervals:
            for i in range(1, len(merged_intervals)):
                gap = merged_intervals[i][0] - merged_intervals[i - 1][1]
                if gap > 0:
                    gaps_ns += gap

        span.orchestration_gaps_ms = gaps_ns / 1_000_000.0
        span.unaccounted_ms = max(
            0.0, span.exclusive_duration_ms - span.orchestration_gaps_ms
        )
    else:
        span.is_leaf = True
        span.child_covered_duration_ms = 0.0
        span.exclusive_duration_ms = span.inclusive_duration_ms
        span.orchestration_gaps_ms = 0.0
        span.unaccounted_ms = 0.0


@dataclasses.dataclass
class RequestAuditContext:
    """Holds granular diagnostic and latency telemetry for an individual AI request."""

    request_id: str
    correlation_id: str | None = None
    traceparent: str | None = None
    start_time: float = dataclasses.field(default_factory=time.perf_counter)
    start_time_ns: int = dataclasses.field(default_factory=time.perf_counter_ns)
    end_time: float | None = None
    end_time_ns: int | None = None
    total_duration_ms: float | None = None
    pipeline_duration_ms: float | None = None
    api_framework_overhead_ms: float | None = None
    success: bool = True
    error_type: str | None = None
    final_stage: str = "init"

    # Hierarchical span model
    root_span: AuditSpan | None = None
    active_spans: list[AuditSpan] = dataclasses.field(default_factory=list)
    all_spans: list[AuditSpan] = dataclasses.field(default_factory=list)

    # Leaf stage durations (monotonic, non-overlapping stage -> elapsed ms)
    leaf_stage_durations_ms: dict[str, float] = dataclasses.field(default_factory=dict)

    # Active span stack: list of (span_name, start_perf_counter, is_leaf)
    span_stack: list[tuple[str, float, bool]] = dataclasses.field(default_factory=list)

    # Granular operation counters
    counts: dict[str, int] = dataclasses.field(
        default_factory=lambda: {
            "llm_calls": 0,
            "backend_calls": 0,
            "retrieval_calls": 0,
            "critic_calls": 0,
            "validation_calls": 0,
            "correction_attempts": 0,
            "cold_loads": 0,
            "duplicate_prompts": 0,
            "duplicate_sql": 0,
            "duplicate_backend_calls": 0,
        }
    )

    # Hash registries for detecting duplicate work within this request
    seen_hashes: dict[str, set[str]] = dataclasses.field(
        default_factory=lambda: {
            "prompt": set(),
            "sql": set(),
            "retrieval": set(),
            "backend": set(),
        }
    )

    # Ordered list of all recorded audit events for this request
    events: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    # Freeform request metadata
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def record_leaf_duration(self, stage_name: str, duration_ms: float) -> None:
        """Add duration to a leaf stage without double counting nested spans."""
        self.leaf_stage_durations_ms[stage_name] = (
            self.leaf_stage_durations_ms.get(stage_name, 0.0) + max(0.0, duration_ms)
        )

    def increment_count(self, key: str, amount: int = 1) -> int:
        """Atomically increment a diagnostic counter."""
        self.counts[key] = self.counts.get(key, 0) + amount
        return self.counts[key]

    def check_and_register_hash(self, category: str, item_hash: str) -> bool:
        """Check if a hash was already seen; returns True if this is a DUPLICATE."""
        if not item_hash:
            return False
        registry = self.seen_hashes.setdefault(category, set())
        if item_hash in registry:
            return True
        registry.add(item_hash)
        return False


_CURRENT_AUDIT: contextvars.ContextVar[RequestAuditContext | None] = (
    contextvars.ContextVar("enterprise_ai_copilot_request_audit", default=None)
)


def get_current_audit() -> RequestAuditContext | None:
    """Retrieve the active RequestAuditContext for the current thread/task."""
    return _CURRENT_AUDIT.get()


def set_current_audit(
    ctx: RequestAuditContext | None,
) -> contextvars.Token[RequestAuditContext | None]:
    """Bind a RequestAuditContext to the current thread/task."""
    return _CURRENT_AUDIT.set(ctx)


def reset_current_audit(
    token: contextvars.Token[RequestAuditContext | None],
) -> None:
    """Restore the previous RequestAuditContext token."""
    _CURRENT_AUDIT.reset(token)


def create_audit_context(
    request_id: str,
    correlation_id: str | None = None,
    traceparent: str | None = None,
    **kwargs: Any,
) -> RequestAuditContext:
    """Create and return a new RequestAuditContext instance."""
    return RequestAuditContext(
        request_id=request_id,
        correlation_id=correlation_id,
        traceparent=traceparent,
        **kwargs,
    )
