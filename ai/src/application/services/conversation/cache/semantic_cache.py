"""Conditional semantic cache with strict safety validation."""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import threading
from typing import Any, Optional

from src.application.services.conversation.state.conversation_state import SemanticQueryState


@dataclass
class SemanticCacheEntry:
    canonical_key: str
    semantic_query_state: SemanticQueryState
    sql: str
    tenant_id: str
    user_id: str
    semantic_revision_id: str
    schema_version: str
    created_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    ttl_seconds: int = 3600

    def is_expired(self, now: Optional[datetime.datetime] = None) -> bool:
        current_time = now or datetime.datetime.now(datetime.timezone.utc)
        return (current_time - self.created_at).total_seconds() > self.ttl_seconds


class ConditionalSemanticCache:
    """Provides conditional semantic reuse only when strictly justified and validated."""

    def __init__(self, enabled: bool = True, max_entries: int = 500) -> None:
        self._enabled = enabled
        self._max_entries = max_entries
        self._cache: dict[str, SemanticCacheEntry] = {}
        self._lock = threading.RLock()

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def lookup_and_validate(
        self,
        candidate_key: str,
        query_state: Optional[SemanticQueryState],
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        semantic_revision_id: str = "active",
        schema_version: str = "default_schema",
    ) -> Optional[SemanticCacheEntry]:
        """Look up entry and strictly validate semantic intent, filters, grouping, and tenant."""
        if not self._enabled:
            return None

        # Reject semantic cache lookup if tenant_id or user_id is missing
        if not tenant_id or not user_id:
            return None

        with self._lock:
            entry = self._cache.get(candidate_key)
            if entry is None or entry.is_expired():
                if entry is not None:
                    del self._cache[candidate_key]
                return None

            # 1. Tenant boundary
            if entry.tenant_id != tenant_id:
                return None

            # 2. Permission / User boundary
            if entry.user_id != user_id:
                return None

            # 3. Revision boundary
            if entry.semantic_revision_id != semantic_revision_id:
                return None

            # 4. Schema boundary
            if entry.schema_version != schema_version:
                return None

            # 5. Semantic intent validation: if query_state is provided, ensure dimensions and filters match
            if query_state is not None:
                cached_qs = entry.semantic_query_state
                # Check dimensions & group by
                if set(cached_qs.group_by) != set(query_state.group_by):
                    return None
                if cached_qs.limit != query_state.limit:
                    return None
                if cached_qs.filters != query_state.filters:
                    return None
                if set(cached_qs.metrics) != set(query_state.metrics):
                    return None

            return entry

    def record(
        self,
        key: str,
        query_state: SemanticQueryState,
        sql: str,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        semantic_revision_id: str = "active",
        schema_version: str = "default_schema",
        ttl_seconds: int = 3600,
    ) -> None:
        if not self._enabled:
            return

        # Never record semantic cache entries without explicit tenant and user keys
        if not tenant_id or not user_id:
            return

        with self._lock:
            if len(self._cache) >= self._max_entries and key not in self._cache:
                oldest = min(self._cache.keys(), key=lambda k: self._cache[k].created_at)
                del self._cache[oldest]

            self._cache[key] = SemanticCacheEntry(
                canonical_key=key,
                semantic_query_state=query_state,
                sql=sql,
                tenant_id=tenant_id,
                user_id=user_id,
                semantic_revision_id=semantic_revision_id,
                schema_version=schema_version,
                ttl_seconds=ttl_seconds,
            )

    def invalidate_revision(self, semantic_revision_id: str) -> int:
        with self._lock:
            keys = [k for k, v in self._cache.items() if v.semantic_revision_id == semantic_revision_id]
            for k in keys:
                del self._cache[k]
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
