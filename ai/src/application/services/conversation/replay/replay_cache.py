"""In-memory thread-safe runtime replay cache."""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import threading
from typing import Any, Optional


@dataclass
class ReplayEntry:
    fingerprint: str
    normalized_question: str
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    semantic_revision_id: str = "active"
    schema_version: str = "default_schema"
    sql: Optional[str] = None
    text_summary: Optional[str] = None
    presentation_type: str = "DataTable"
    is_success: bool = True
    is_negative_result: bool = False
    negative_outcome_type: Optional[str] = None  # e.g., "NO_ROWS_FOUND"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime.datetime = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    ttl_seconds: int = 3600

    def is_expired(self, now: Optional[datetime.datetime] = None) -> bool:
        current_time = now or datetime.datetime.now(datetime.timezone.utc)
        age = (current_time - self.created_at).total_seconds()
        return age > self.ttl_seconds


class InMemoryReplayRepository:
    """Thread-safe bounded in-memory runtime cache for exact replays."""

    def __init__(self, max_entries: int = 1000, default_ttl_seconds: int = 3600) -> None:
        self._max_entries = max(10, max_entries)
        self._default_ttl_seconds = default_ttl_seconds
        self._store: dict[str, ReplayEntry] = {}
        self._lock = threading.RLock()

    def get(self, fingerprint: str) -> Optional[ReplayEntry]:
        with self._lock:
            entry = self._store.get(fingerprint)
            if entry is None:
                return None
            if entry.is_expired():
                del self._store[fingerprint]
                return None
            return entry

    def save(self, entry: ReplayEntry) -> None:
        # Strictly reject saving entries that lack security context
        if not entry.tenant_id or not entry.user_id:
            return

        with self._lock:
            # If at capacity, evict oldest entry
            if len(self._store) >= self._max_entries and entry.fingerprint not in self._store:
                oldest_key = min(self._store.keys(), key=lambda k: self._store[k].created_at)
                del self._store[oldest_key]

            self._store[entry.fingerprint] = entry

    def invalidate_by_revision(self, semantic_revision_id: str) -> int:
        with self._lock:
            keys_to_delete = [
                k for k, v in self._store.items()
                if v.semantic_revision_id == semantic_revision_id
            ]
            for k in keys_to_delete:
                del self._store[k]
            return len(keys_to_delete)

    def invalidate_by_tenant(self, tenant_id: str) -> int:
        with self._lock:
            keys_to_delete = [
                k for k, v in self._store.items()
                if v.tenant_id == tenant_id
            ]
            for k in keys_to_delete:
                del self._store[k]
            return len(keys_to_delete)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._store)
