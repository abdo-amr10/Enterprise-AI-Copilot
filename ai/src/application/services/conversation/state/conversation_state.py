"""Structured state models for the Conversation Layer."""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class SemanticQueryState:
    """Structured semantic representation of an active or continued query.

    Never mutates raw SQL strings directly. Continuations operate by modifying
    this semantic representation.
    """
    entities: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    dimensions: tuple[str, ...] = ()
    filters: dict[str, Any] = field(default_factory=dict)
    group_by: tuple[str, ...] = ()
    order_by: tuple[str, ...] = ()
    limit: Optional[int] = None
    time_range: Optional[str] = None
    raw_sql: Optional[str] = None

    def clone_with(
        self,
        *,
        entities: Optional[tuple[str, ...]] = None,
        metrics: Optional[tuple[str, ...]] = None,
        dimensions: Optional[tuple[str, ...]] = None,
        filters: Optional[dict[str, Any]] = None,
        group_by: Optional[tuple[str, ...]] = None,
        order_by: Optional[tuple[str, ...]] = None,
        limit: Optional[int] = -999,  # sentinel
        time_range: Optional[str] = -999,  # sentinel
        raw_sql: Optional[str] = None,
    ) -> SemanticQueryState:
        return SemanticQueryState(
            entities=self.entities if entities is None else entities,
            metrics=self.metrics if metrics is None else metrics,
            dimensions=self.dimensions if dimensions is None else dimensions,
            filters=dict(self.filters) if filters is None else filters,
            group_by=self.group_by if group_by is None else group_by,
            order_by=self.order_by if order_by is None else order_by,
            limit=self.limit if limit == -999 else limit,
            time_range=self.time_range if time_range == -999 else time_range,
            raw_sql=self.raw_sql if raw_sql is None else raw_sql,
        )


@dataclass(frozen=True)
class ExecutionRecord:
    """Metadata about a previous query execution."""
    sql: str
    status: str
    timestamp: str
    row_count: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    # The question this execution answered. Required for full-history
    # similarity search (see conversation/retrieval/turn_retriever.py) --
    # without it, a stored execution can't be matched against a new
    # question at all.
    user_question: Optional[str] = None


@dataclass(frozen=True)
class ResultMetadata:
    """Structured metadata about an executed query result."""
    columns: tuple[str, ...] = ()
    row_count: int = 0
    sample_rows: tuple[tuple[Any, ...], ...] = ()
    summary: Optional[str] = None
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    security_scope: Optional[str] = None


@dataclass(frozen=True)
class NegativeResultRecord:
    """Explicitly modeled negative outcome to prevent generic 'not found' collapse."""
    outcome_type: str  # "NO_ROWS_FOUND", "SCHEMA_ENTITY_NOT_FOUND", "UNSUPPORTED_REQUEST", etc.
    question: str
    timestamp: str
    details: Optional[str] = None


@dataclass
class ConversationState:
    """Compact, authoritative conversation state.

    Maintains versioning to avoid concurrency race conditions and supports
    isolated runtime caching while respecting Backend as the persistent system of record.
    """
    conversation_id: str
    state_version: int = 1
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    semantic_revision_id: Optional[str] = None
    schema_version: Optional[str] = None
    active_query_state: Optional[SemanticQueryState] = None
    last_successful_execution: Optional[ExecutionRecord] = None
    last_result_metadata: Optional[ResultMetadata] = None
    last_request_fingerprint: Optional[str] = None
    # Additive: full history of successful executions for this
    # conversation (bounded, see MAX_EXECUTION_HISTORY below).
    # `last_successful_execution` above always mirrors execution_history[-1]
    # for backward compatibility with existing readers.
    execution_history: list[ExecutionRecord] = field(default_factory=list)
    negative_results: dict[str, NegativeResultRecord] = field(default_factory=dict)
    updated_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    MAX_EXECUTION_HISTORY = 200

    def append_execution(self, record: ExecutionRecord) -> None:
        """Appends to history (bounded) and keeps last_successful_execution in sync."""
        self.execution_history.append(record)
        if len(self.execution_history) > self.MAX_EXECUTION_HISTORY:
            self.execution_history = self.execution_history[-self.MAX_EXECUTION_HISTORY:]
        self.last_successful_execution = record

    def increment_version(self) -> int:
        self.state_version += 1
        self.updated_at = datetime.datetime.now(datetime.timezone.utc)
        return self.state_version
