"""Authoritative Conversation Router implementing the complete priority cascade."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional
import uuid

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.backend.copilot.text_to_sql_runtime_response import (
    TextToSQLRuntimeResponse,
)
from src.application.services.conversation.cache.semantic_cache import (
    ConditionalSemanticCache,
)
from src.application.services.conversation.continuation.continuation_resolver import (
    ContinuationResolver,
)
from src.application.services.conversation.followup.followup_detector import (
    FollowupDetector,
)
from src.application.services.conversation.followup.models import FollowupConfidence
from src.application.services.conversation.normalization.normalizer import (
    RequestNormalizer,
)
from src.application.services.conversation.persistence.backend_state_adapter import (
    BackendStateAdapter,
)
from src.application.services.conversation.replay.replay_manager import (
    ExactReplayManager,
)
from src.application.services.conversation.result_resolution.models import (
    ResultResolutionStatus,
)
from src.application.services.conversation.result_resolution.result_resolver import (
    ResultResolver,
)
from src.application.services.conversation.router.routing_decision import (
    ConversationRoute,
    RoutingDecision,
)
from src.application.services.conversation.router.scope_guard import ScopeGuard
from src.application.services.conversation.state.state_manager import (
    ConversationStateManager,
)

logger = logging.getLogger(__name__)


class ConversationRouter:
    """Authoritative single router orchestrating the cheapest-path conversation cascade.

    1. Normalize
    2. Minimal state load (Backend payload + Runtime cache)
    3. Exact replay check
    4. Previous-result resolution (No SQL / No LLM)
    5. Follow-up detection & continuation (Semantic update, no SQL replace)
    6. Early scope guard / safe rejection (Before Text-to-SQL)
    7. Conditional semantic reuse
    8. Independent database query -> Existing Text-to-SQL
    9. State update & persistence
    """

    def __init__(
        self,
        *,
        replay_manager: Optional[ExactReplayManager] = None,
        state_manager: Optional[ConversationStateManager] = None,
        result_resolver: Optional[ResultResolver] = None,
        followup_detector: Optional[FollowupDetector] = None,
        continuation_resolver: Optional[ContinuationResolver] = None,
        semantic_cache: Optional[ConditionalSemanticCache] = None,
    ) -> None:
        self._replay_manager = replay_manager or ExactReplayManager()
        self._state_manager = state_manager or ConversationStateManager()
        self._result_resolver = result_resolver or ResultResolver()
        self._followup_detector = followup_detector or FollowupDetector()
        self._continuation_resolver = continuation_resolver or ContinuationResolver()
        self._semantic_cache = semantic_cache or ConditionalSemanticCache(enabled=True)

    @property
    def replay_manager(self) -> ExactReplayManager:
        return self._replay_manager

    @property
    def state_manager(self) -> ConversationStateManager:
        return self._state_manager

    @property
    def result_resolver(self) -> ResultResolver:
        return self._result_resolver

    @property
    def followup_detector(self) -> FollowupDetector:
        return self._followup_detector

    @property
    def continuation_resolver(self) -> ContinuationResolver:
        return self._continuation_resolver

    @property
    def semantic_cache(self) -> ConditionalSemanticCache:
        return self._semantic_cache

    def route(
        self,
        question: str,
        raw_conversation: tuple[dict[str, Any], ...] = (),
        *,
        correlation_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        branch_id: Optional[str] = None,
        semantic_revision_id: Optional[str] = None,
        schema_version: Optional[str] = None,
        conversation_id: Optional[str] = None,
        last_result_metadata: Optional[dict[str, Any]] = None,
        executor: Optional[Callable[[CopilotAskRequest], TextToSQLRuntimeResponse]] = None,
    ) -> RoutingDecision:
        """Route the user request through the authoritative cascade."""
        if conversation_id and str(conversation_id).strip():
            conv_id = str(conversation_id).strip()
        elif correlation_id and str(correlation_id).strip():
            conv_id = f"corr_{str(correlation_id).strip()}"
        else:
            conv_id = f"ephem_{uuid.uuid4().hex[:12]}"

        # ----------------------------------------------------------------------
        # 1. Normalization
        # ----------------------------------------------------------------------
        normalized_q = RequestNormalizer.normalize(question)
        if not normalized_q:
            return RoutingDecision(
                route=ConversationRoute.UNSUPPORTED,
                is_success=False,
                error_message="VALIDATION_ERROR: Question cannot be empty.",
                reason_for_fallback="Empty normalized query.",
            )

        # ----------------------------------------------------------------------
        # 2. Minimal State Load (Backend payload + Runtime cache)
        # ----------------------------------------------------------------------
        state = self._state_manager.get_or_create_state(
            conv_id,
            tenant_id=tenant_id,
            user_id=user_id,
            semantic_revision_id=semantic_revision_id,
            schema_version=schema_version,
        )

        # Ingest explicit last_result_metadata if supplied in request
        if last_result_metadata and isinstance(last_result_metadata, dict):
            extracted = BackendStateAdapter.extract_state(
                conv_id,
                raw_conversation,
                tenant_id=tenant_id,
                user_id=user_id,
                semantic_revision_id=semantic_revision_id,
                schema_version=schema_version,
                last_result_metadata_dict=last_result_metadata,
            )
            if extracted.last_result_metadata is not None:
                state.last_result_metadata = extracted.last_result_metadata
        elif state.last_successful_execution is None and raw_conversation:
            backend_state = BackendStateAdapter.extract_state(
                conv_id,
                raw_conversation,
                tenant_id=tenant_id,
                user_id=user_id,
                semantic_revision_id=semantic_revision_id,
                schema_version=schema_version,
            )
            if backend_state.last_successful_execution is not None:
                state.last_successful_execution = backend_state.last_successful_execution
                state.active_query_state = backend_state.active_query_state
            if backend_state.last_result_metadata is not None:
                state.last_result_metadata = backend_state.last_result_metadata

        has_history = bool(raw_conversation or state.last_successful_execution)

        # ----------------------------------------------------------------------
        # 3. Exact Replay Check
        # ----------------------------------------------------------------------
        replay = self._replay_manager.lookup(
            question,
            tenant_id=tenant_id,
            user_id=user_id,
            semantic_revision_id=semantic_revision_id,
            schema_version=schema_version,
            conversation_id=conv_id,
        )

        if replay.is_valid and replay.entry is not None:
            logger.info("Exact replay cache hit for question: %s", normalized_q)
            return RoutingDecision(
                route=ConversationRoute.EXACT_REPLAY,
                is_success=replay.entry.is_success,
                generated_sql=replay.entry.sql,
                text_summary=replay.entry.text_summary,
                presentation_type=replay.entry.presentation_type,
                cache_hit=True,
                cache_type="EXACT_REPLAY",
                state_loaded=True,
            )

        # ----------------------------------------------------------------------
        # 4. Result-Aware Resolution (No SQL / No LLM)
        # ----------------------------------------------------------------------
        res_outcome = self._result_resolver.resolve(
            question,
            state.last_result_metadata,
            summary=state.last_result_metadata.summary if state.last_result_metadata else None,
            current_tenant_id=tenant_id,
            current_user_id=user_id,
        )

        if res_outcome.status == ResultResolutionStatus.ANSWERABLE and res_outcome.answer:
            logger.info("Answered directly from previous result without SQL or LLM.")
            self._state_manager.record_result_answer(conv_id, question=question, answer=res_outcome.answer)
            return RoutingDecision(
                route=ConversationRoute.RESULT_ANSWER,
                is_success=True,
                generated_sql=None,
                text_summary=res_outcome.answer,
                direct_answer=res_outcome.answer,
                presentation_type="DirectAnswer",
                state_loaded=True,
                result_resolution="ANSWERABLE",
            )

        # ----------------------------------------------------------------------
        # 5. Follow-Up Detection & Continuation
        # ----------------------------------------------------------------------
        followup = self._followup_detector.detect(question, state, has_history=has_history)

        if followup.confidence_level == FollowupConfidence.UNRESOLVED:
            return RoutingDecision(
                route=ConversationRoute.UNRESOLVED_CONTEXT,
                is_success=False,
                error_message=(
                    "I'm not sure what that's referring to. Could you clarify which "
                    "previous question or result you mean?"
                ),
                state_loaded=True,
                followup_detected=True,
                followup_confidence="UNRESOLVED",
            )

        if followup.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED:
            prior_q = None
            if raw_conversation:
                for raw in reversed(raw_conversation):
                    if isinstance(raw, dict):
                        if raw.get("user_question"):
                            prior_q = raw["user_question"]
                            break
                        if raw.get("role") == "user" and raw.get("content"):
                            prior_q = raw["content"]
                            break

            continuation = self._continuation_resolver.resolve(
                question,
                state,
                followup,
                prior_question=prior_q,
            )

            if continuation.is_resolved and executor:
                # A related request still needs a fresh database execution,
                # but when its fully resolved intent has been seen before we
                # can safely reuse its validated SQL and skip Text-to-SQL.
                # The replay key includes the conversation, user, tenant,
                # semantic revision, and schema version.
                resolved_replay = self._replay_manager.lookup(
                    continuation.resolved_question,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    semantic_revision_id=semantic_revision_id,
                    schema_version=schema_version,
                    conversation_id=conv_id,
                )
                if resolved_replay.is_valid and resolved_replay.entry is not None:
                    cached_sql = resolved_replay.entry.sql
                    if cached_sql:
                        self._state_manager.record_successful_execution(
                            conv_id,
                            sql=cached_sql,
                            question=continuation.resolved_question,
                            query_state=continuation.updated_semantic_state,
                            fingerprint=(
                                resolved_replay.fingerprint.fingerprint_hash
                                if resolved_replay.fingerprint else None
                            ),
                        )
                        return RoutingDecision(
                            route=ConversationRoute.FOLLOW_UP_QUERY,
                            is_success=True,
                            generated_sql=cached_sql,
                            resolved_question=continuation.resolved_question,
                            cache_hit=True,
                            cache_type="RESOLVED_FOLLOW_UP_REPLAY",
                            state_loaded=True,
                            followup_detected=True,
                            followup_confidence=followup.confidence_level.value,
                        )

                exec_req = CopilotAskRequest(
                    question=continuation.resolved_question,
                    conversation=raw_conversation,
                    correlation_id=correlation_id,
                )
                logger.info(
                    "Executing continued query [%s] via existing Text-to-SQL",
                    continuation.resolved_question,
                )
                runtime_resp = executor(exec_req)

                if runtime_resp.status == "Success" and runtime_resp.sql:
                    self._state_manager.record_successful_execution(
                        conv_id,
                        sql=runtime_resp.sql,
                        question=continuation.resolved_question or question,
                        query_state=continuation.updated_semantic_state,
                        fingerprint=replay.fingerprint.fingerprint_hash if replay.fingerprint else None,
                    )
                    self._replay_manager.record_success(
                        question,
                        runtime_resp.sql,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        semantic_revision_id=semantic_revision_id,
                        schema_version=schema_version,
                        conversation_id=conv_id,
                    )
                    # Keep a second exact key for the canonical resolved
                    # question, allowing equivalent follow-up wording to
                    # skip the Text-to-SQL model on later turns.
                    if continuation.resolved_question != question:
                        self._replay_manager.record_success(
                            continuation.resolved_question,
                            runtime_resp.sql,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            semantic_revision_id=semantic_revision_id,
                            schema_version=schema_version,
                            conversation_id=conv_id,
                        )
                    return RoutingDecision(
                        route=ConversationRoute.FOLLOW_UP_QUERY,
                        is_success=True,
                        generated_sql=runtime_resp.sql,
                        resolved_question=continuation.resolved_question,
                        state_loaded=True,
                        followup_detected=True,
                        followup_confidence=followup.confidence_level.value,
                        text_to_sql_called=True,
                    )
                else:
                    self._state_manager.record_execution_failure(
                        conv_id,
                        sql=runtime_resp.sql,
                        error_code=runtime_resp.error_code or "SQL_GENERATION_FAILED",
                        error_message=runtime_resp.failure_reason or runtime_resp.message or "Execution failed",
                    )
                    return RoutingDecision(
                        route=ConversationRoute.EXECUTION_ERROR,
                        is_success=False,
                        error_message=runtime_resp.failure_reason or runtime_resp.message or runtime_resp.error_code,
                        resolved_question=continuation.resolved_question,
                        state_loaded=True,
                        followup_detected=True,
                        text_to_sql_called=True,
                    )

        # ----------------------------------------------------------------------
        # 6. Early Scope Guard / Safe Rejection (BEFORE Text-to-SQL)
        # ----------------------------------------------------------------------
        scope_eval = ScopeGuard.evaluate(question)
        if not scope_eval.is_in_scope:
            logger.info("Scope guard safely rejected out-of-scope question: %s", normalized_q)
            self._state_manager.record_unsupported_request(conv_id)
            return RoutingDecision(
                route=ConversationRoute.UNSUPPORTED,
                is_success=False,
                error_message=scope_eval.rejection_message,
                reason_for_fallback=scope_eval.reason,
            )

        # ----------------------------------------------------------------------
        # 7. Conditional Semantic Reuse
        # ----------------------------------------------------------------------
        sem_entry = self._semantic_cache.lookup_and_validate(
            normalized_q,
            state.active_query_state,
            tenant_id=tenant_id,
            user_id=user_id,
            semantic_revision_id=semantic_revision_id or "active",
            schema_version=schema_version or "default_schema",
        )
        if sem_entry is not None:
            logger.info("Conditional semantic cache hit for question: %s", normalized_q)
            return RoutingDecision(
                route=ConversationRoute.SEMANTIC_REUSE,
                is_success=True,
                generated_sql=sem_entry.sql,
                cache_hit=True,
                cache_type="SEMANTIC",
                semantic_lookup_used=True,
            )

        # ----------------------------------------------------------------------
        # 8. Supported Database Query -> Existing Text-to-SQL
        # ----------------------------------------------------------------------
        if executor:
            exec_req = CopilotAskRequest(
                question=question,
                conversation=raw_conversation,
                correlation_id=correlation_id,
            )
            logger.info("Delegating independent query [%s] to existing Text-to-SQL", question)
            runtime_resp = executor(exec_req)

            if runtime_resp.status == "Success" and runtime_resp.sql:
                self._state_manager.record_successful_execution(
                    conv_id,
                    sql=runtime_resp.sql,
                    question=question,
                    fingerprint=replay.fingerprint.fingerprint_hash if replay.fingerprint else None,
                )
                self._replay_manager.record_success(
                    question,
                    runtime_resp.sql,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    semantic_revision_id=semantic_revision_id,
                    schema_version=schema_version,
                    conversation_id=conv_id,
                )
                return RoutingDecision(
                    route=ConversationRoute.NEW_DATABASE_QUERY,
                    is_success=True,
                    generated_sql=runtime_resp.sql,
                    state_loaded=True,
                    text_to_sql_called=True,
                )
            else:
                self._state_manager.record_execution_failure(
                    conv_id,
                    sql=runtime_resp.sql,
                    error_code=runtime_resp.error_code or "SQL_GENERATION_FAILED",
                    error_message=runtime_resp.failure_reason or runtime_resp.message or "Execution failed",
                )
                return RoutingDecision(
                    route=ConversationRoute.EXECUTION_ERROR,
                    is_success=False,
                    error_message=runtime_resp.failure_reason or runtime_resp.message or runtime_resp.error_code,
                    state_loaded=True,
                    text_to_sql_called=True,
                )

        # If no executor supplied (e.g. standalone router test)
        return RoutingDecision(
            route=ConversationRoute.NEW_DATABASE_QUERY,
            is_success=True,
            resolved_question=question,
            state_loaded=True,
        )
