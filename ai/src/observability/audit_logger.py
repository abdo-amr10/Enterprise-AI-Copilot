"""Thread-safe JSON Lines file logger for latency audit telemetry."""
from __future__ import annotations

import datetime
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()


def get_audit_log_path() -> Path:
    """Resolve the target path for structured JSONL audit logs."""
    custom_path = os.getenv("LATENCY_AUDIT_LOG_FILE")
    if custom_path:
        return Path(custom_path).resolve()
    # Default to logs/latency_audit.jsonl in the ai workspace directory
    base_dir = Path(os.getenv("WORKSPACE_ROOT", "."))
    return (base_dir / "logs" / "latency_audit.jsonl").resolve()


def is_audit_enabled() -> bool:
    """Return True if latency audit logging is enabled."""
    val = os.getenv("LATENCY_AUDIT_ENABLED", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def write_audit_event(event: dict[str, Any]) -> None:
    """Append a single structured JSON event to the audit log file.

    Fails open: never raises exceptions or interrupts application execution.
    """
    if not is_audit_enabled():
        return

    try:
        # Guarantee timestamp exists
        if "timestamp" not in event:
            event["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        serialized = json.dumps(event, default=str, ensure_ascii=False) + "\n"

        target_path = get_audit_log_path()
        with _LOCK:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "a", encoding="utf-8") as f:
                f.write(serialized)
    except Exception as exc:
        # Fallback to standard logging to ensure fail-open safety
        logger.debug("Failed writing latency audit event: %s", exc)
