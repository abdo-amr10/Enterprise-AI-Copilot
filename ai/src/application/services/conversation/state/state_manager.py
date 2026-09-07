"""Thread-safe Conversation State Manager with versioning and concurrency controls."""

from __future__ import annotations

from collections import defaultdict
import datetime
import logging
import threading
from typing import Any, Optional

from src.application.services.conversation.state.conversation_state import (
    ConversationState,
    ExecutionRecord,
    NegativeResultRecord,
    ResultMetadata,
    SemanticQueryState,
)

logger = logging.getLogger(__name__)


class ConversationStateManager:
    """Manages thread-safe conversation state lifecycle and concurrency."""

    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}
        self._locks: dict[str, threading.RLock] = defaultdict(threading.RLock)
        self._global_lock = threading.RLock()

    def get_or_create_state(
        self,
        conversation_id: str,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        semantic_revision_id: Optional[str] = None,
        schema_version: Optional[str] = None,
    ) -> ConversationState:
        with self._global_lock:
            conv_lock = self._locks[conversation_id]

        with conv_lock:
            if conversation_id not in self._states:
                self._states[conversation_id] = ConversationState(
                    conversation_id=conversation_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    semantic_revision_id=semantic_revision_id,
                    schema_version=schema_version,
                )
            else:
                state = self._states[conversation_id]
                # Update context if newly provided
                if tenant_id and not state.tenant_id:
                    state.tenant_id = tenant_id
                if user_id and not state.user_id:
                    state.user_id = user_id
                if semantic_revision_id:
                    state.semantic_revision_id = semantic_revision_id
                if schema_version:
                    state.schema_version = schema_version
            return self._states[conversation_id]

    def record_successful_execution(
        self,
        conversation_id: str,
        *,
        sql: str,
        query_state: Optional[SemanticQueryState] = None,
        result_metadata: Optional[ResultMetadata] = None,
        fingerprint: Optional[str] = None,
        row_count: Optional[int] = None,
    ) -> ConversationState:
        """Update state after a successful database query execution."""
        with self._global_lock:
            conv_lock = self._locks[conversation_id]

        with conv_lock:
            state = self.get_or_create_state(conversation_id)
            state.last_successful_execution = ExecutionRecord(
                sql=sql,
                status="Success",
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                row_count=row_count,
                tenant_id=state.tenant_id,
                user_id=state.user_id,
            )
            if query_state is not None:
                state.active_query_state = query_state
            elif sql:
                # If query_state wasn't explicitly built, retain raw_sql
                state.active_query_state = SemanticQueryState(raw_sql=sql)

            if result_metadata is not None:
                state.last_result_metadata = result_metadata

            if fingerprint:
                state.last_request_fingerprint = fingerprint

            state.increment_version()
            logger.debug("Conversation %s updated to state_version %d", conversation_id, state.state_version)
            return state

    def record_result_answer(
        self,
        conversation_id: str,
        *,
        question: str,
        answer: str,
    ) -> ConversationState:
        """Update state after a result-answer-only response.

        Critically: does NOT overwrite or corrupt active_query_state.
        """
        with self._global_lock:
            conv_lock = self._locks[conversation_id]

        with conv_lock:
            state = self.get_or_create_state(conversation_id)
            # Active database query state remains unchanged.
            state.updated_at = datetime.datetime.now(datetime.timezone.utc)
            return state

    def record_execution_failure(
        self,
        conversation_id: str,
        *,
        sql: Optional[str],
        error_code: str,
        error_message: str,
    ) -> ConversationState:
        """Update state after an execution failure.

        Critically: does NOT promote failed state to active successful state.
        """
        with self._global_lock:
            conv_lock = self._locks[conversation_id]

        with conv_lock:
            state = self.get_or_create_state(conversation_id)
            # Do NOT update last_successful_execution with failed query
            state.updated_at = datetime.datetime.now(datetime.timezone.utc)
            return state

    def record_negative_result(
        self,
        conversation_id: str,
        *,
        question: str,
        outcome_type: str,
        details: Optional[str] = None,
    ) -> ConversationState:
        """Record zero rows or entity not found without treating as universal truth."""
        with self._global_lock:
            conv_lock = self._locks[conversation_id]

        with conv_lock:
            state = self.get_or_create_state(conversation_id)
            state.negative_results[question] = NegativeResultRecord(
                outcome_type=outcome_type,
                question=question,
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                details=details,
            )
            state.increment_version()
            return state

    def record_unsupported_request(self, conversation_id: str) -> ConversationState:
        """Unsupported request does NOT corrupt or alter active state."""
        with self._global_lock:
            conv_lock = self._locks[conversation_id]

        with conv_lock:
            state = self.get_or_create_state(conversation_id)
            # State remains completely uncorrupted
            return state

    def clear(self, conversation_id: Optional[str] = None) -> None:
        with self._global_lock:
            if conversation_id is not None:
                self._states.pop(conversation_id, None)
                self._locks.pop(conversation_id, None)
            else:
                self._states.clear()
                self._locks.clear()
