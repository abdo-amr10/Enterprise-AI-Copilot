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
    def _parse_result_metadata(
        cls,
        payload: dict[str, Any],
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Optional[ResultMetadata]:
        """Tolerant parser for ResultMetadata supporting flat or nested backend payloads."""
        if not isinstance(payload, dict):
            return None

        # Check for nested 'result' wrapper from .NET Backend
        container = payload.get("result") if isinstance(payload.get("result"), dict) else payload

        # Check for nested TableData / tableData / table_data
        table_data = (
            container.get("TableData")
            or container.get("tableData")
            or container.get("table_data")
            or {}
        )
        if not isinstance(table_data, dict):
            table_data = {}

        # 1. Columns
        cols_raw = (
            table_data.get("Columns")
            or table_data.get("columns")
            or container.get("columns")
            or container.get("Columns")
            or payload.get("columns")
            or payload.get("Columns")
            or ()
        )

        # 2. Rows
        rows_raw = (
            table_data.get("Rows")
            or table_data.get("rows")
            or container.get("rows")
            or container.get("Rows")
            or container.get("sample_rows")
            or container.get("sampleRows")
            or payload.get("rows")
            or payload.get("sample_rows")
            or ()
        )

        # 3. Fallback to 'Data' / 'data' list of dicts if TableData was empty
        if not rows_raw:
            data_list = container.get("Data") or container.get("data") or payload.get("data") or payload.get("Data")
            if isinstance(data_list, list) and data_list and isinstance(data_list[0], dict):
                seen_cols: dict[str, None] = {}
                for row_dict in data_list:
                    if isinstance(row_dict, dict):
                        for k in row_dict.keys():
                            seen_cols[str(k)] = None
                if not cols_raw:
                    cols_raw = tuple(seen_cols.keys())
                rows_raw = [
                    [row_dict.get(c) for c in cols_raw]
                    for row_dict in data_list
                    if isinstance(row_dict, dict)
                ]

        columns = tuple(str(c) for c in cols_raw)
        sample_rows = tuple(tuple(r) for r in rows_raw)

        # 4. Row count
        rc_raw = (
            table_data.get("TotalRows")
            or table_data.get("totalRows")
            or container.get("TotalRows")
            or container.get("totalRows")
            or container.get("rowCount")
            or container.get("row_count")
            or payload.get("rowCount")
            or payload.get("row_count")
            or len(sample_rows)
        )
        try:
            row_count = int(rc_raw)
        except (ValueError, TypeError):
            row_count = len(sample_rows)

        # 5. Summary
        summary = (
            container.get("TextSummary")
            or container.get("textSummary")
            or container.get("summary")
            or container.get("Summary")
            or payload.get("TextSummary")
            or payload.get("textSummary")
            or payload.get("summary")
            or payload.get("Summary")
        )

        if not columns and not sample_rows and not summary and row_count == 0:
            return None

        return ResultMetadata(
            columns=columns,
            row_count=row_count,
            sample_rows=sample_rows[:50],
            summary=str(summary) if summary else None,
            tenant_id=tenant_id,
            user_id=user_id,
        )

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
            parsed_meta = cls._parse_result_metadata(
                last_result_metadata_dict, tenant_id=tenant_id, user_id=user_id
            )
            if parsed_meta:
                state.last_result_metadata = parsed_meta

        if not raw_conversation:
            return state

        # Walk turns FORWARD (oldest first) so execution_history preserves
        # chronological order, building the full history instead of
        # stopping at the first match found. last_successful_execution /
        # last_result_metadata still end up as the most recent one, same
        # as before, via append_execution's side effect.
        for raw in raw_conversation:
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

                question_text = raw.get("user_question") or raw.get("userQuestion")
                summary = raw.get("execution_result_summary") or raw.get("text_summary") or raw.get("textSummary")
                exec_res = raw.get("execution_result") or raw.get("executionResult")

                if sql:
                    record = ExecutionRecord(
                        sql=str(sql),
                        status=str(raw.get("execution_status") or raw.get("status") or "Success"),
                        timestamp=str(raw.get("timestamp") or ""),
                        row_count=raw.get("row_count") or raw.get("rowCount"),
                        tenant_id=tenant_id,
                        user_id=user_id,
                        user_question=str(question_text) if question_text else None,
                    )
                    state.append_execution(record)
                    if state.active_query_state is None:
                        state.active_query_state = SemanticQueryState(raw_sql=str(sql))

                if exec_res or summary:
                    meta_payload = dict(exec_res) if isinstance(exec_res, dict) else {}
                    if summary and "summary" not in meta_payload and "TextSummary" not in meta_payload:
                        meta_payload["summary"] = summary

                    parsed_turn_meta = cls._parse_result_metadata(
                        meta_payload, tenant_id=tenant_id, user_id=user_id
                    )
                    if parsed_turn_meta:
                        state.last_result_metadata = parsed_turn_meta

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
