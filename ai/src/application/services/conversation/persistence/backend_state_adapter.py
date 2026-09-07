"""Adapter bridging Backend-owned persistence with AI Runtime ConversationState.

The Backend remains the authoritative persistent system of record. This adapter
reconstructs structured ConversationState from what the Backend transmits on each
call (via CopilotAskRequest.conversation) and defines the exact serialization format
for Backend persistence.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.application.services.conversation.state.conversation_state import (
    ConversationState,
    ExecutionRecord,
    ResultMetadata,
    SemanticQueryState,
)

logger = logging.getLogger(__name__)


class BackendStateAdapter:
    """Extracts and serializes ConversationState from/to Backend payload contracts."""

    @classmethod
    def extract_state(
        cls,
        conversation_id: str,
        raw_conversation: tuple[dict[str, Any], ...],
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        semantic_revision_id: Optional[str] = None,
        schema_version: Optional[str] = None,
        last_result_metadata_dict: Optional[dict[str, Any]] = None,
    ) -> ConversationState:
        """Construct ConversationState strictly from the Backend-provided payload."""
        state = ConversationState(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            semantic_revision_id=semantic_revision_id,
            schema_version=schema_version,
        )

        # Ingest explicit last_result_metadata if supplied in the request payload
        if last_result_metadata_dict and isinstance(last_result_metadata_dict, dict):
            cols = tuple(last_result_metadata_dict.get("columns") or ())
            raw_rows = last_result_metadata_dict.get("rows") or last_result_metadata_dict.get("sample_rows") or ()
            rows = tuple(tuple(r) for r in raw_rows)
            rc = int(last_result_metadata_dict.get("row_count") or last_result_metadata_dict.get("rowCount") or len(rows))
            summ = last_result_metadata_dict.get("summary")
            state.last_result_metadata = ResultMetadata(
                columns=cols,
                row_count=rc,
                sample_rows=rows[:50],
                summary=str(summ) if summ else None,
                tenant_id=tenant_id,
                user_id=user_id,
            )

        if not raw_conversation:
            return state

        # Inspect turns in reverse to locate the latest successful execution and result
        for raw in reversed(raw_conversation):
            if not isinstance(raw, dict):
                continue

            # Check for structured state attached by backend
            if "state" in raw and isinstance(raw["state"], dict):
                raw_st = raw["state"]
                state.state_version = int(raw_st.get("state_version", 1))
                if "active_query_state" in raw_st and isinstance(raw_st["active_query_state"], dict):
                    aqs = raw_st["active_query_state"]
                    state.active_query_state = SemanticQueryState(
                        entities=tuple(aqs.get("entities", ())),
                        metrics=tuple(aqs.get("metrics", ())),
                        dimensions=tuple(aqs.get("dimensions", ())),
                        filters=dict(aqs.get("filters", {})),
                        group_by=tuple(aqs.get("group_by", ())),
                        order_by=tuple(aqs.get("order_by", ())),
                        limit=aqs.get("limit"),
                        time_range=aqs.get("time_range"),
                        raw_sql=aqs.get("raw_sql"),
                    )

            # Check for turn or assistant message convention
            role = raw.get("role")
            if role in ("turn", "assistant"):
                sql = raw.get("generated_sql") or raw.get("generatedSql") or raw.get("sql")
                if not sql and raw.get("content") and "Generated SQL:" in raw["content"]:
                    parts = raw["content"].split("Generated SQL:", 1)
                    if len(parts) > 1 and parts[1].strip():
                        sql = parts[1].strip()

                summary = raw.get("execution_result_summary") or raw.get("text_summary") or raw.get("textSummary")
                exec_res = raw.get("execution_result") or raw.get("executionResult")

                if sql and state.last_successful_execution is None:
                    state.last_successful_execution = ExecutionRecord(
                        sql=str(sql),
                        status=str(raw.get("execution_status") or raw.get("status") or "Success"),
                        timestamp=str(raw.get("timestamp") or ""),
                        row_count=raw.get("row_count") or raw.get("rowCount"),
                        tenant_id=tenant_id,
                        user_id=user_id,
                    )
                    if state.active_query_state is None:
                        state.active_query_state = SemanticQueryState(raw_sql=str(sql))

                if (exec_res or summary) and state.last_result_metadata is None:
                    columns: tuple[str, ...] = ()
                    rows: tuple[tuple[Any, ...], ...] = ()
                    row_count = 0

                    if isinstance(exec_res, dict):
                        columns = tuple(exec_res.get("columns") or ())
                        rows = tuple(tuple(r) for r in (exec_res.get("rows") or ()))
                        row_count = int(exec_res.get("rowCount") or exec_res.get("row_count") or len(rows))

                    state.last_result_metadata = ResultMetadata(
                        columns=columns,
                        row_count=row_count,
                        sample_rows=rows[:50],  # bounded sample
                        summary=str(summary) if summary else None,
                        tenant_id=tenant_id,
                        user_id=user_id,
                    )

            # If both execution and result found, stop scanning history
            if state.last_successful_execution is not None and state.last_result_metadata is not None:
                break

        return state

    @classmethod
    def serialize_state(cls, state: ConversationState) -> dict[str, Any]:
        """Serialize ConversationState for the Backend persistence contract."""
        data: dict[str, Any] = {
            "conversation_id": state.conversation_id,
            "state_version": state.state_version,
            "updated_at": state.updated_at.isoformat(),
        }

        if state.active_query_state:
            qs = state.active_query_state
            data["active_query_state"] = {
                "entities": list(qs.entities),
                "metrics": list(qs.metrics),
                "dimensions": list(qs.dimensions),
                "filters": qs.filters,
                "group_by": list(qs.group_by),
                "order_by": list(qs.order_by),
                "limit": qs.limit,
                "time_range": qs.time_range,
                "raw_sql": qs.raw_sql,
            }

        if state.last_successful_execution:
            exe = state.last_successful_execution
            data["last_successful_execution"] = {
                "sql": exe.sql,
                "status": exe.status,
                "timestamp": exe.timestamp,
                "row_count": exe.row_count,
            }

        if state.last_result_metadata:
            meta = state.last_result_metadata
            data["last_result_metadata"] = {
                "columns": list(meta.columns),
                "row_count": meta.row_count,
                "summary": meta.summary,
            }

        return data
