"""Structured runtime conversation trace logger.

Appends [CONVERSATION_TRACE] blocks to logs/conversation_trace.log and emits to Python logging.
"""

from __future__ import annotations

import logging
from pathlib import Path
import threading

logger = logging.getLogger("conversation_trace")

_LOGS_DIR = Path(__file__).resolve().parents[3] / "logs"
_TRACE_FILE = _LOGS_DIR / "conversation_trace.log"
_LOCK = threading.Lock()


def log_trace(stage: str, trace_id: str, **kwargs: object) -> None:
    """Log a structured [CONVERSATION_TRACE] block."""
    lines = [
        "[CONVERSATION_TRACE]",
        f"stage={stage}",
        f"trace_id={trace_id}",
    ]
    for key, value in kwargs.items():
        if value is not None:
            lines.append(f"{key}={value}")

    block = "\n".join(lines) + "\n\n"
    logger.info("%s", block.strip())

    try:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with open(_TRACE_FILE, "a", encoding="utf-8") as f:
                f.write(block)
    except Exception as exc:
        logger.warning("Failed writing to conversation_trace.log: %s", exc)
