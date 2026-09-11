"""Authoritative Conversation Router implementing the complete priority cascade."""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional
import uuid

from src.observability.conversation_trace_logger import log_trace

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
from src.application.services.conversation.extraction.slot_extractor import (
    SlotExtractor,
)
from src.application.services.conversation.followup.followup_detector import (
    FollowupDetector,
)
from src.application.services.conversation.followup.models import (
    FollowupConfidence,
    FollowupDetectionResult,
    FollowupType,
)
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
from src.application.services.conversation.router.scope_guard import (
    ScopeGuard,
    _OUT_OF_SCOPE_MESSAGE,
)
from src.application.services.conversation.semantic_routing.application.semantic_intent_router import (
    SemanticIntentRouter,
)
from src.application.services.conversation.semantic_routing.domain.intent import (
    ConversationIntent,
)
from src.application.services.conversation.state.conversation_state import (
    ResultMetadata,
)
from src.application.services.conversation.state.state_manager import (
    ConversationStateManager,
)

logger = logging.getLogger(__name__)

_UNSET = object()


class ConversationRouter:
    """Authoritative single router orchestrating the cheapest-path conversation cascade.

    1. Normalize
    2. Minimal state load (Backend payload + Runtime cache)
    3. Exact replay check
    4. Previous-result resolution (No SQL / No LLM)
    5. Semantic Intent Classification & Follow-up detection
    6. Early scope guard / safe rejection (Before Text-to-SQL)
    7. Conditional semantic reuse
    8. Independent database query -> Existing Text-to-SQL
    9. State update & persistence
    """

    _WORD_TO_NUM = SlotExtractor._WORD_TO_NUM

    def __init__(
        self,
        *,
        replay_manager: Optional[ExactReplayManager] = None,
        state_manager: Optional[ConversationStateManager] = None,
        result_resolver: Optional[ResultResolver] = None,
        followup_detector: Optional[FollowupDetector] = None,
        continuation_resolver: Optional[ContinuationResolver] = None,
        semantic_cache: Optional[ConditionalSemanticCache] = None,
        semantic_router: Any = _UNSET,
        slot_extractor: Optional[SlotExtractor] = None,
        llm_intent_classifier: Any = _UNSET,
    ) -> None:
        self._replay_manager = replay_manager or ExactReplayManager()
        self._state_manager = state_manager or ConversationStateManager()
        self._result_resolver = result_resolver or ResultResolver()
        self._followup_detector = followup_detector or FollowupDetector()
        self._continuation_resolver = continuation_resolver or ContinuationResolver()
        self._semantic_cache = semantic_cache or ConditionalSemanticCache(enabled=True)
        self._slot_extractor = slot_extractor or SlotExtractor()

        if llm_intent_classifier is not _UNSET:
            self._llm_intent_classifier = llm_intent_classifier
        else:
            self._llm_intent_classifier = None

        if semantic_router is not _UNSET:
            self._semantic_router: Optional[SemanticIntentRouter] = semantic_router
        else:
            try:
                from src.config.conversation_settings import CONVERSATION_SETTINGS
                if CONVERSATION_SETTINGS.semantic_router_enabled:
                    self._semantic_router = SemanticIntentRouter.get_shared_instance()
                else:
                    self._semantic_router = None
            except Exception as e:
                logger.warning("Failed to initialize SemanticIntentRouter: %s", e)
                self._semantic_router = None

    @property
    def llm_intent_classifier(self) -> Optional[Any]:
        return self._llm_intent_classifier

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

    @property
    def semantic_router(self) -> Optional[SemanticIntentRouter]:
        return self._semantic_router

    @property
    def slot_extractor(self) -> SlotExtractor:
        return self._slot_extractor

    @classmethod
    def _map_intent_to_followup_type(cls, intent: ConversationIntent) -> FollowupType:
        mapping = {
            ConversationIntent.LIMIT_CHANGE: FollowupType.LIMIT_CHANGE,
            ConversationIntent.SORT_CHANGE: FollowupType.SORT_CHANGE,
            ConversationIntent.GROUP_BY_CHANGE: FollowupType.GROUP_BY_CHANGE,
            ConversationIntent.FILTER_CHANGE: FollowupType.FILTER_CHANGE,
            ConversationIntent.CORRECTION: FollowupType.CORRECTION,
            ConversationIntent.PRONOUN_REFERENCE: FollowupType.PRONOUN_REFERENCE,
        }
        return mapping.get(intent, FollowupType.FILTER_CHANGE)

    @classmethod
    def _extract_slot_for_intent(cls, intent: ConversationIntent, text: str) -> str:
        """Delegate slot extraction to SlotExtractor."""
        return SlotExtractor.extract_slot(intent, text)

    @staticmethod
    def _extract_clean_question_after_reset(text: str) -> Optional[str]:
        """Delegate clean question extraction to SlotExtractor."""
        return SlotExtractor.extract_clean_question_after_reset(text)

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
        llm_used = False
        if conversation_id and str(conversation_id).strip():
            conv_id = str(conversation_id).strip()
        elif correlation_id and str(correlation_id).strip():
            conv_id = f"corr_{str(correlation_id).strip()}"
        else:
            conv_id = f"ephem_{uuid.uuid4().hex[:12]}"

        # Derive effective tenant scope (authoritative RLS context from tenant_id or branch_id)
        effective_tenant_id = (tenant_id or branch_id or "").strip() or None

        _trace_id = correlation_id or conv_id or "no-trace-id"
        log_trace(
            "conversation_router.entry",
            _trace_id,
            question=question,
            conv_id=conv_id,
            raw_conversation_count=len(raw_conversation) if raw_conversation else 0,
            last_result_metadata_present=last_result_metadata is not None,
        )

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

        logger.debug(
            "conversation.normalized_query=%s conv_id=%s tenant_id=%s branch_id=%s",
            normalized_q,
            conv_id,
            effective_tenant_id,
            branch_id,
        )

        # ----------------------------------------------------------------------
        # 2. Minimal State Load (Backend payload + Runtime cache)
        # ----------------------------------------------------------------------
        state = self._state_manager.get_or_create_state(
            conv_id,
            tenant_id=effective_tenant_id,
            user_id=user_id,
            semantic_revision_id=semantic_revision_id,
            schema_version=schema_version,
        )

        # Ingest explicit last_result_metadata if supplied in request
        if last_result_metadata and isinstance(last_result_metadata, dict):
            extracted = BackendStateAdapter.extract_state(
                conv_id,
                raw_conversation,
                tenant_id=effective_tenant_id,
                user_id=user_id,
                semantic_revision_id=semantic_revision_id,
                schema_version=schema_version,
                last_result_metadata_dict=last_result_metadata,
            )
            if extracted.last_result_metadata is not None:
                state.last_result_metadata = extracted.last_result_metadata
            if extracted.last_successful_execution is not None:
                state.last_successful_execution = extracted.last_successful_execution
            if extracted.active_query_state is not None:
                state.active_query_state = extracted.active_query_state
        elif isinstance(last_result_metadata, ResultMetadata):
            state.last_result_metadata = last_result_metadata
        elif state.last_successful_execution is None and raw_conversation:
            backend_state = BackendStateAdapter.extract_state(
                conv_id,
                raw_conversation,
                tenant_id=effective_tenant_id,
                user_id=user_id,
                semantic_revision_id=semantic_revision_id,
                schema_version=schema_version,
            )
            if backend_state.last_successful_execution is not None:
                state.last_successful_execution = backend_state.last_successful_execution
                state.active_query_state = backend_state.active_query_state
            if backend_state.last_result_metadata is not None:
                state.last_result_metadata = backend_state.last_result_metadata

        log_trace(
            "conversation_router.state",
            _trace_id,
            last_successful_execution_present=state.last_successful_execution is not None,
            last_successful_question=getattr(state.last_successful_execution, "user_question", None) if state.last_successful_execution else None,
            last_result_metadata_present=state.last_result_metadata is not None,
            active_query_state_present=state.active_query_state is not None,
            pending_clarification=state.pending_clarification is not None,
        )

        # Dialog continuation: if there's a pending clarification request from previous turn
        if state.pending_clarification:
            orig_question = state.pending_clarification.get("original_question", "")
            clarified_question = f"{orig_question} ({question})".strip()
            state.pending_clarification = None
            logger.info("Continuing dialog with pending clarification: %s", clarified_question)
            question = clarified_question
            normalized_q = RequestNormalizer.normalize(question)

        has_history = bool(raw_conversation or state.last_successful_execution)
        logger.debug("conversation.state_loaded=True has_history=%s", has_history)

        # ----------------------------------------------------------------------
        # 3. Exact Replay Check
        # ----------------------------------------------------------------------
        replay = self._replay_manager.lookup(
            question,
            tenant_id=effective_tenant_id,
            user_id=user_id,
            semantic_revision_id=semantic_revision_id,
            schema_version=schema_version,
            conversation_id=conv_id,
        )
        logger.debug("conversation.exact_replay.hit=%s", replay.is_valid and replay.entry is not None)

        if replay.is_valid and replay.entry is not None:
            logger.info("Exact replay cache hit for question: %s (negative=%s)", normalized_q, replay.entry.is_negative_result)
            if replay.entry.is_negative_result:
                return RoutingDecision(
                    route=ConversationRoute.EXACT_REPLAY,
                    is_success=False,
                    generated_sql=None,
                    text_summary=replay.entry.text_summary or "No results found for this query.",
                    direct_answer=replay.entry.text_summary or "No results found for this query.",
                    error_message=replay.entry.metadata.get("error_message") if replay.entry.metadata else None,
                    presentation_type="DirectAnswer",
                    cache_hit=True,
                    cache_type="NEGATIVE_REPLAY",
                    state_loaded=True,
                )
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

        # Negative result check from state
        neg_record = state.negative_results.get(question) or state.negative_results.get(normalized_q)
        if neg_record:
            logger.info("Negative result state hit for question: %s", normalized_q)
            return RoutingDecision(
                route=ConversationRoute.EXACT_REPLAY,
                is_success=False,
                generated_sql=None,
                text_summary=neg_record.details or "No results found for this query.",
                direct_answer=neg_record.details or "No results found for this query.",
                error_message=neg_record.details,
                presentation_type="DirectAnswer",
                cache_hit=True,
                cache_type="NEGATIVE_REPLAY",
                state_loaded=True,
            )

        # ----------------------------------------------------------------------
        # 4. Result-Aware Resolution (No SQL / No LLM)
        # ----------------------------------------------------------------------
        res_outcome = self._result_resolver.resolve(
            question,
            state.last_result_metadata,
            summary=state.last_result_metadata.summary if state.last_result_metadata else None,
            current_tenant_id=effective_tenant_id,
            current_user_id=user_id,
        )

        log_trace(
            "conversation_router.result_resolution",
            _trace_id,
            status=res_outcome.status.value if hasattr(res_outcome.status, "value") else str(res_outcome.status),
            answer_present=res_outcome.answer is not None,
            answer_preview=res_outcome.answer[:200] if res_outcome.answer else None,
            metadata_present=state.last_result_metadata is not None,
        )

        logger.debug(
            "conversation.result_resolver.hit=%s",
            res_outcome.status == ResultResolutionStatus.ANSWERABLE,
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
        # 5. Semantic Intent Classification & Follow-Up Continuation
        # ----------------------------------------------------------------------
        # Step 5a: Follow-Up & Reset Detection (Deterministic checks)
        followup = self._followup_detector.detect(question, state, has_history=has_history)
        logger.debug(
            "conversation.followup.detected=%s confidence=%s is_reset=%s",
            followup.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED,
            followup.confidence_level.value,
            followup.is_context_reset,
        )

        # Context Reset: intentionally reset conversation state if requested
        if followup.is_context_reset:
            logger.info("Explicit context reset requested. Resetting state for conv_id: %s", conv_id)
            self._state_manager.clear(conv_id)
            state = self._state_manager.get_or_create_state(
                conv_id,
                tenant_id=effective_tenant_id,
                user_id=user_id,
                semantic_revision_id=semantic_revision_id,
                schema_version=schema_version,
            )
            raw_conversation = ()
            has_history = False
            clean_q = followup.clean_question or self._slot_extractor.extract_clean_question_after_reset(normalized_q)
            if clean_q:
                question = clean_q
                normalized_q = RequestNormalizer.normalize(question)
                followup = self._followup_detector.detect(question, state, has_history=False)
            else:
                return RoutingDecision(
                    route=ConversationRoute.NEW_DATABASE_QUERY,
                    is_success=True,
                    direct_answer="Conversation context has been reset. What would you like to ask?",
                    text_summary="Conversation context has been reset.",
                    presentation_type="DirectAnswer",
                    state_loaded=True,
                    semantic_intent=ConversationIntent.RESET_CONTEXT.value,
                    semantic_confidence=1.0,
                )

        semantic_result = None
        semantic_intent = None
        semantic_conf = None

        if self._semantic_router is not None:
            semantic_result = self._semantic_router.classify(
                question, state=state, has_history=has_history
            )
            semantic_intent = semantic_result.intent
            semantic_conf = semantic_result.confidence_score
            logger.debug(
                "conversation.semantic_router.classified intent=%s score=%.4f margin=%.4f",
                semantic_intent.value,
                semantic_conf,
                semantic_result.margin,
            )

            # Semantic context reset fallback (if deterministic didn't catch the reset phrase)
            if semantic_intent == ConversationIntent.RESET_CONTEXT:
                logger.info("Semantic context reset requested. Resetting state for conv_id: %s", conv_id)
                self._state_manager.clear(conv_id)
                state = self._state_manager.get_or_create_state(
                    conv_id,
                    tenant_id=effective_tenant_id,
                    user_id=user_id,
                    semantic_revision_id=semantic_revision_id,
                    schema_version=schema_version,
                )
                raw_conversation = ()
                has_history = False
                clean_q = self._slot_extractor.extract_clean_question_after_reset(normalized_q)
                if clean_q:
                    question = clean_q
                    normalized_q = RequestNormalizer.normalize(question)
                    followup = self._followup_detector.detect(question, state, has_history=False)
                    semantic_result = self._semantic_router.classify(question, state=state, has_history=False)
                    semantic_intent = semantic_result.intent
                    semantic_conf = semantic_result.confidence_score
                else:
                    return RoutingDecision(
                        route=ConversationRoute.NEW_DATABASE_QUERY,
                        is_success=True,
                        direct_answer="Conversation context has been reset. What would you like to ask?",
                        text_summary="Conversation context has been reset.",
                        presentation_type="DirectAnswer",
                        state_loaded=True,
                        semantic_intent=semantic_intent.value,
                        semantic_confidence=semantic_conf,
                    )

            # Direct capability answer (bypasses Text-to-SQL)
            if semantic_intent == ConversationIntent.CAPABILITY and not (
                has_history and followup.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED
            ):
                direct_ans = (
                    "I am your Enterprise AI Copilot. I can query and analyze enterprise data, "
                    "filter records, aggregate metrics across departments or time periods, "
                    "sort results, and answer questions from your previous query results."
                )
                return RoutingDecision(
                    route=ConversationRoute.CAPABILITY,
                    is_success=True,
                    text_summary=direct_ans,
                    direct_answer=direct_ans,
                    presentation_type="DirectAnswer",
                    state_loaded=True,
                    semantic_intent=semantic_intent.value,
                    semantic_confidence=semantic_conf,
                )

            # Out-of-scope safe rejection
            if semantic_intent == ConversationIntent.OUT_OF_SCOPE:
                logger.info("Semantic router safely rejected out-of-scope question: %s", normalized_q)
                self._state_manager.record_unsupported_request(conv_id)
                return RoutingDecision(
                    route=ConversationRoute.UNSUPPORTED,
                    is_success=False,
                    error_message=_OUT_OF_SCOPE_MESSAGE,
                    reason_for_fallback="Semantic router classified question as OUT_OF_SCOPE.",
                    state_loaded=True,
                    semantic_intent=semantic_intent.value,
                    semantic_confidence=semantic_conf,
                )

            # Ambiguous / Unresolved intent
            if semantic_intent == ConversationIntent.AMBIGUOUS:
                if (
                    followup.confidence_level != FollowupConfidence.FOLLOW_UP_CONFIRMED
                    and followup.reason not in (
                        "Complete standalone question.",
                        "Standalone question prefixed with conversational conjunction.",
                    )
                ):
                    if self._llm_intent_classifier is not None:
                        try:
                            llm_result = self._llm_intent_classifier.classify(
                                question, has_history=has_history
                            )
                            llm_used = True
                            if llm_result.intent != ConversationIntent.AMBIGUOUS:
                                logger.info(
                                    "LLM intent fallback resolved ambiguous query '%s' to %s",
                                    normalized_q,
                                    llm_result.intent.value,
                                )
                                semantic_intent = llm_result.intent
                                semantic_conf = llm_result.confidence_score
                                if semantic_intent.is_followup and has_history:
                                    op_type = self._map_intent_to_followup_type(semantic_intent)
                                    target_val = self._slot_extractor.extract_slot(semantic_intent, normalized_q)
                                    followup = FollowupDetectionResult(
                                        confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                                        operation_type=op_type,
                                        target_value=target_val,
                                        confidence_score=semantic_conf,
                                        reason=f"LLM fallback classified as {semantic_intent.value}",
                                    )
                                elif semantic_intent == ConversationIntent.NEW_DATABASE_QUERY:
                                    followup = FollowupDetectionResult(
                                        confidence_level=FollowupConfidence.INDEPENDENT,
                                        confidence_score=semantic_conf,
                                        reason="LLM fallback classified as NEW_DATABASE_QUERY.",
                                    )
                        except Exception as e:
                            logger.warning("LLM intent classifier fallback failed: %s", e)

                    if semantic_intent == ConversationIntent.AMBIGUOUS:
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
                            semantic_intent=semantic_intent.value,
                            semantic_confidence=semantic_conf,
                            llm_used_by_conversation_layer=llm_used,
                        )

        # Rule 1: Respect unresolved clarification requests (e.g. ambiguous entity mention like "And merchants?")
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
                semantic_intent=semantic_intent.value if semantic_intent else None,
                semantic_confidence=semantic_conf,
            )

        # Rule 2: Check if followup detector verified a complete standalone question
        is_standalone = followup.reason in (
            "Complete standalone question.",
            "Standalone question prefixed with conversational conjunction.",
        )

        # Rule 3: Enhance Follow-Up with Semantic Router insights
        if (
            semantic_intent in (
                ConversationIntent.LIMIT_CHANGE,
                ConversationIntent.SORT_CHANGE,
                ConversationIntent.GROUP_BY_CHANGE,
                ConversationIntent.FILTER_CHANGE,
                ConversationIntent.CORRECTION,
                ConversationIntent.PRONOUN_REFERENCE,
            )
            and followup.confidence_level != FollowupConfidence.FOLLOW_UP_CONFIRMED
            and not is_standalone
            and has_history
        ):
            op_type = self._map_intent_to_followup_type(semantic_intent)
            target_val = self._slot_extractor.extract_slot(semantic_intent, normalized_q)
            followup = FollowupDetectionResult(
                confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
                operation_type=op_type,
                target_value=target_val,
                confidence_score=semantic_conf or 0.9,
                reason=f"Semantic router classified as {semantic_intent.value}",
            )
        elif (
            (semantic_intent == ConversationIntent.NEW_DATABASE_QUERY or is_standalone)
            and followup.confidence_level != FollowupConfidence.FOLLOW_UP_CONFIRMED
        ):
            followup = FollowupDetectionResult(
                confidence_level=FollowupConfidence.INDEPENDENT,
                confidence_score=semantic_conf or 1.0,
                reason=followup.reason or "Semantic router classified as NEW_DATABASE_QUERY.",
            )

        log_trace(
            "conversation_router.followup_detector",
            _trace_id,
            confidence_level=followup.confidence_level.value if hasattr(followup.confidence_level, "value") else str(followup.confidence_level),
            confidence_score=followup.confidence_score,
            reason=followup.reason,
        )

        if followup.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED:
            prior_q = None
            prior_sql = None
            source_used = "none"

            # 1. Check for explicit "go back to <target>" command
            go_back_match = re.search(
                r"\bgo\s+back\s+to\s+(?:the\s+)?(.+?)(?:\s+from\s+before)?(?:\s+and\b|$)",
                normalized_q,
                re.IGNORECASE,
            )
            if go_back_match:
                target_phrase = go_back_match.group(1).strip().lower()
                target_tokens = [w for w in re.split(r"\s+", target_phrase) if len(w) > 2 or w.isdigit()]

                # First search state execution history (reverse order)
                if state and state.execution_history:
                    for rec in reversed(state.execution_history):
                        if rec.user_question and all(tok in rec.user_question.lower() for tok in target_tokens):
                            prior_q = rec.user_question
                            prior_sql = rec.sql
                            source_used = "execution_history_goback"
                            break

                # If not found, search raw_conversation
                if not prior_q and raw_conversation:
                    for raw in reversed(raw_conversation):
                        if isinstance(raw, dict):
                            q_cand = raw.get("user_question") or raw.get("userQuestion") or raw.get("question") or (
                                raw.get("content") if str(raw.get("role") or "").lower() in ("user", "turn") else None
                            )
                            if q_cand and all(tok in str(q_cand).lower() for tok in target_tokens):
                                prior_q = str(q_cand).strip()
                                prior_sql = raw.get("generated_sql") or raw.get("generatedSql") or raw.get("sql")
                                source_used = "raw_conversation_goback"
                                break

            # 2. If not "go back to" or target not found, retrieve the active/successful context turn
            if not prior_q and state and state.execution_history:
                # Find the most recent successful execution record
                for rec in reversed(state.execution_history):
                    if rec.status in ("Completed", "Success") and rec.user_question:
                        prior_q = rec.user_question
                        prior_sql = rec.sql
                        source_used = "execution_history_last_success"
                        break

            if not prior_q and state and state.last_successful_execution and state.last_successful_execution.user_question:
                prior_q = state.last_successful_execution.user_question
                prior_sql = state.last_successful_execution.sql
                source_used = "last_successful_execution"

            # 3. Check raw_conversation backwards, skipping failed/rejected turns
            if not prior_q and raw_conversation:
                for raw in reversed(raw_conversation):
                    if isinstance(raw, dict):
                        status = str(raw.get("execution_status") or raw.get("status") or "").strip().lower()
                        if status in ("failed", "error", "rejected"):
                            continue  # Skip failed/rejected turns!
                        q_candidate = raw.get("user_question") or raw.get("userQuestion") or raw.get("question")
                        if not q_candidate:
                            role = str(raw.get("role") or "").strip().lower()
                            if role in ("user", "turn") and raw.get("content"):
                                q_candidate = raw["content"]
                        if q_candidate:
                            prior_q = str(q_candidate).strip()
                            prior_sql = raw.get("generated_sql") or raw.get("generatedSql") or raw.get("sql")
                            source_used = "raw_conversation"
                            break

            # 4. Fallback to last_result_metadata
            if not prior_q and last_result_metadata and isinstance(last_result_metadata, dict):
                meta_q = last_result_metadata.get("question") or last_result_metadata.get("userQuestion") or last_result_metadata.get("user_question")
                if meta_q:
                    prior_q = str(meta_q).strip()
                    prior_sql = last_result_metadata.get("generatedSql") or last_result_metadata.get("sql")
                    source_used = "last_result_metadata"

            # Fallback to active query state raw_sql if prior_sql still not set
            if not prior_sql and state and state.active_query_state and state.active_query_state.raw_sql:
                prior_sql = state.active_query_state.raw_sql

            log_trace(
                "conversation_router.continuation.prior_question",
                _trace_id,
                prior_question=prior_q,
                prior_sql=prior_sql,
                source=source_used,
            )

            continuation = self._continuation_resolver.resolve(
                question,
                state,
                followup,
                prior_question=prior_q,
                prior_sql=prior_sql,
            )

            log_trace(
                "conversation_router.continuation.output",
                _trace_id,
                resolved_question=continuation.resolved_question,
                is_resolved=continuation.is_resolved,
                original_question=question,
            )

            logger.debug(
                "conversation.canonical_query=%s resolved=%s",
                continuation.resolved_question,
                continuation.is_resolved,
            )

            if continuation.is_resolved and executor:
                # A related request still needs a fresh database execution,
                # but when its fully resolved intent has been seen before we
                # can safely reuse its validated SQL and skip Text-to-SQL.
                # The replay key includes the conversation, user, tenant,
                # semantic revision, and schema version.
                resolved_replay = self._replay_manager.lookup(
                    continuation.resolved_question,
                    tenant_id=effective_tenant_id,
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
                            semantic_intent=semantic_intent.value if semantic_intent else None,
                            semantic_confidence=semantic_conf,
                            llm_used_by_conversation_layer=llm_used,
                        )

                augmented_convo = list(raw_conversation) if raw_conversation else []
                scope_summary = self._continuation_resolver._extract_base_entity_scope(prior_q or "")
                if scope_summary:
                    augmented_convo.append({
                        "role": "system",
                        "content": f"CONVERSATION_CONTEXT: Established active entity scope: {scope_summary}",
                    })

                exec_req = CopilotAskRequest(
                    question=continuation.resolved_question,
                    conversation=tuple(augmented_convo),
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
                        tenant_id=effective_tenant_id,
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
                            tenant_id=effective_tenant_id,
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
                        semantic_intent=semantic_intent.value if semantic_intent else None,
                        semantic_confidence=semantic_conf,
                        llm_used_by_conversation_layer=llm_used,
                    )
                elif runtime_resp.status in ("ClarificationNeeded", "NeedsClarification"):
                    state.pending_clarification = {
                        "original_question": continuation.resolved_question or question,
                        "clarification_request": runtime_resp.message or runtime_resp.failure_reason,
                    }
                    return RoutingDecision(
                        route=ConversationRoute.UNRESOLVED_CONTEXT,
                        is_success=False,
                        error_message=runtime_resp.message or runtime_resp.failure_reason,
                        direct_answer=runtime_resp.message or runtime_resp.failure_reason,
                        text_summary=runtime_resp.message or runtime_resp.failure_reason,
                        resolved_question=continuation.resolved_question,
                        presentation_type="DirectAnswer",
                        state_loaded=True,
                        followup_detected=True,
                        text_to_sql_called=True,
                        semantic_intent=semantic_intent.value if semantic_intent else None,
                        semantic_confidence=semantic_conf,
                    )
                else:
                    self._state_manager.record_execution_failure(
                        conv_id,
                        sql=runtime_resp.sql,
                        error_code=runtime_resp.error_code or "SQL_GENERATION_FAILED",
                        error_message=runtime_resp.failure_reason or runtime_resp.message or "Execution failed",
                    )
                    self._state_manager.record_negative_result(
                        conv_id,
                        question=continuation.resolved_question or question,
                        outcome_type=runtime_resp.error_code or "SQL_GENERATION_FAILED",
                        details=runtime_resp.failure_reason or runtime_resp.message or "Execution failed",
                    )
                    self._replay_manager.record_negative_result(
                        question,
                        outcome_type=runtime_resp.error_code or "SQL_GENERATION_FAILED",
                        text_summary=runtime_resp.failure_reason or runtime_resp.message or "Execution failed",
                        tenant_id=effective_tenant_id,
                        user_id=user_id,
                        semantic_revision_id=semantic_revision_id,
                        schema_version=schema_version,
                        conversation_id=conv_id,
                        metadata={"error_message": runtime_resp.failure_reason or runtime_resp.message},
                    )
                    return RoutingDecision(
                        route=ConversationRoute.EXECUTION_ERROR,
                        is_success=False,
                        error_message=runtime_resp.failure_reason or runtime_resp.message or runtime_resp.error_code,
                        resolved_question=continuation.resolved_question,
                        state_loaded=True,
                        followup_detected=True,
                        text_to_sql_called=True,
                        semantic_intent=semantic_intent.value if semantic_intent else None,
                        semantic_confidence=semantic_conf,
                    )
            elif continuation.is_resolved:
                return RoutingDecision(
                    route=ConversationRoute.FOLLOW_UP_QUERY,
                    is_success=True,
                    resolved_question=continuation.resolved_question,
                    state_loaded=True,
                    followup_detected=True,
                    followup_confidence=followup.confidence_level.value,
                    semantic_intent=semantic_intent.value if semantic_intent else None,
                    semantic_confidence=semantic_conf,
                )

        # ----------------------------------------------------------------------
        # 6. Early Scope Guard / Safe Rejection (BEFORE Text-to-SQL)
        # ----------------------------------------------------------------------
        scope_eval = ScopeGuard.evaluate(question)
        logger.debug("conversation.scope_guard.decision=%s", "IN_SCOPE" if scope_eval.is_in_scope else "REJECTED")
        if not scope_eval.is_in_scope:
            logger.info("Scope guard safely rejected out-of-scope question: %s", normalized_q)
            self._state_manager.record_unsupported_request(conv_id)
            return RoutingDecision(
                route=ConversationRoute.UNSUPPORTED,
                is_success=False,
                error_message=scope_eval.rejection_message,
                reason_for_fallback=scope_eval.reason,
                semantic_intent=semantic_intent.value if semantic_intent else None,
                semantic_confidence=semantic_conf,
            )

        # ----------------------------------------------------------------------
        # 7. Conditional Semantic Reuse
        # ----------------------------------------------------------------------
        sem_entry = self._semantic_cache.lookup_and_validate(
            normalized_q,
            state.active_query_state,
            tenant_id=effective_tenant_id,
            user_id=user_id,
            semantic_revision_id=semantic_revision_id or "active",
            schema_version=schema_version or "default_schema",
        )
        logger.debug("conversation.semantic_reuse.hit=%s", sem_entry is not None)
        if sem_entry is not None:
            logger.info("Conditional semantic cache hit for question: %s", normalized_q)
            return RoutingDecision(
                route=ConversationRoute.SEMANTIC_REUSE,
                is_success=True,
                generated_sql=sem_entry.sql,
                cache_hit=True,
                cache_type="SEMANTIC",
                semantic_lookup_used=True,
                semantic_intent=semantic_intent.value if semantic_intent else None,
                semantic_confidence=semantic_conf,
            )

        # ----------------------------------------------------------------------
        # 8. Supported Database Query -> Existing Text-to-SQL
        # ----------------------------------------------------------------------
        if executor:
            # For independent database queries, isolate context: do NOT pass previous user/assistant
            # conversation turns to CopilotAskRequest to prevent LLM prompt contamination.
            # Only pass system-level correction feedback (e.g. RLS_CORRECTION) if present.
            system_corrections = tuple(
                msg for msg in raw_conversation
                if isinstance(msg, dict) and msg.get("role") == "system"
            )
            exec_req = CopilotAskRequest(
                question=question,
                conversation=system_corrections,
                correlation_id=correlation_id,
            )
            logger.info("Delegating independent query [%s] to existing Text-to-SQL (isolated prompt context)", question)
            logger.debug("conversation.sql_generation.invoked=True")
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
                    tenant_id=effective_tenant_id,
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
                    semantic_intent=semantic_intent.value if semantic_intent else None,
                    semantic_confidence=semantic_conf,
                )
            elif runtime_resp.status in ("ClarificationNeeded", "NeedsClarification"):
                state.pending_clarification = {
                    "original_question": question,
                    "clarification_request": runtime_resp.message or runtime_resp.failure_reason,
                }
                return RoutingDecision(
                    route=ConversationRoute.UNRESOLVED_CONTEXT,
                    is_success=False,
                    error_message=runtime_resp.message or runtime_resp.failure_reason,
                    direct_answer=runtime_resp.message or runtime_resp.failure_reason,
                    text_summary=runtime_resp.message or runtime_resp.failure_reason,
                    presentation_type="DirectAnswer",
                    state_loaded=True,
                    text_to_sql_called=True,
                    semantic_intent=semantic_intent.value if semantic_intent else None,
                    semantic_confidence=semantic_conf,
                )
            else:
                self._state_manager.record_execution_failure(
                    conv_id,
                    sql=runtime_resp.sql,
                    error_code=runtime_resp.error_code or "SQL_GENERATION_FAILED",
                    error_message=runtime_resp.failure_reason or runtime_resp.message or "Execution failed",
                )
                self._state_manager.record_negative_result(
                    conv_id,
                    question=question,
                    outcome_type=runtime_resp.error_code or "SQL_GENERATION_FAILED",
                    details=runtime_resp.failure_reason or runtime_resp.message or "Execution failed",
                )
                self._replay_manager.record_negative_result(
                    question,
                    outcome_type=runtime_resp.error_code or "SQL_GENERATION_FAILED",
                    text_summary=runtime_resp.failure_reason or runtime_resp.message or "Execution failed",
                    tenant_id=effective_tenant_id,
                    user_id=user_id,
                    semantic_revision_id=semantic_revision_id,
                    schema_version=schema_version,
                    conversation_id=conv_id,
                    metadata={"error_message": runtime_resp.failure_reason or runtime_resp.message},
                )
                return RoutingDecision(
                    route=ConversationRoute.EXECUTION_ERROR,
                    is_success=False,
                    error_message=runtime_resp.failure_reason or runtime_resp.message or runtime_resp.error_code,
                    state_loaded=True,
                    text_to_sql_called=True,
                    semantic_intent=semantic_intent.value if semantic_intent else None,
                    semantic_confidence=semantic_conf,
                )

        # If no executor supplied (e.g. standalone router test)
        return RoutingDecision(
            route=ConversationRoute.NEW_DATABASE_QUERY,
            is_success=True,
            resolved_question=question,
            state_loaded=True,
            semantic_intent=semantic_intent.value if semantic_intent else None,
            semantic_confidence=semantic_conf,
        )
