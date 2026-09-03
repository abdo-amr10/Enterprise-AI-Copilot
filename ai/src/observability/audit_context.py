"""Request-scoped audit context with contextvars propagation and metric tracking."""
from __future__ import annotations

import contextvars
import dataclasses
import time
from typing import Any


@dataclasses.dataclass
class RequestAuditContext:
    """Holds granular diagnostic and latency telemetry for an individual AI request."""

    request_id: str
    correlation_id: str | None = None
    traceparent: str | None = None
    start_time: float = dataclasses.field(default_factory=time.perf_counter)
    end_time: float | None = None
    total_duration_ms: float | None = None
    success: bool = True
    error_type: str | None = None
    final_stage: str = "init"

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
