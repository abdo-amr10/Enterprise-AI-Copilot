"""Semantic Intent Router providing local, embedding-based intent classification."""

from __future__ import annotations

import logging
from typing import Optional

from src.application.services.conversation.normalization.normalizer import (
    RequestNormalizer,
)
from src.application.services.conversation.semantic_routing.domain.classification_result import (
    IntentClassificationResult,
)
from src.application.services.conversation.semantic_routing.domain.intent import (
    ConversationIntent,
)
from src.application.services.conversation.semantic_routing.infrastructure.embedding_provider import (
    IntentEmbeddingProvider,
)
from src.application.services.conversation.semantic_routing.infrastructure.intent_prototype_store import (
    IntentPrototypeStore,
)
from src.application.services.conversation.state.conversation_state import (
    ConversationState,
)

logger = logging.getLogger(__name__)


_DEFAULT_ROUTER_INSTANCE: Optional[SemanticIntentRouter] = None


class SemanticIntentRouter:
    """Classifies user conversational intent semantically using local embeddings.

    Adheres strictly to Clean Architecture:
    - Encodes query once.
    - Compares against precomputed prototype embeddings in memory.
    - Evaluates confidence thresholds and best-vs-second margin.
    - Incorporates compact conversation state for context awareness.
    - Does NOT extract structured slot parameters (dates, numbers, entities).
    - Does NOT execute SQL or perform security validation.
    """

    def __init__(
        self,
        embedding_provider: IntentEmbeddingProvider,
        prototype_store: IntentPrototypeStore,
        *,
        min_similarity: float = 0.40,
        min_margin: float = 0.05,
    ) -> None:
        self._provider = embedding_provider
        self._store = prototype_store
        self._min_similarity = float(min_similarity)
        self._min_margin = float(min_margin)

    @classmethod
    def get_shared_instance(cls) -> SemanticIntentRouter:
        """Return a shared singleton instance initialized with default catalog."""
        global _DEFAULT_ROUTER_INSTANCE
        if _DEFAULT_ROUTER_INSTANCE is None:
            _DEFAULT_ROUTER_INSTANCE = cls.create_default()
        return _DEFAULT_ROUTER_INSTANCE

    @classmethod
    def create_default(
        cls,
        *,
        model_path: str | Path | None = None,
        min_similarity: float | None = None,
        min_margin: float | None = None,
        device: str | None = None,
    ) -> SemanticIntentRouter:
        """Factory method to construct a router using default configuration and prototype catalog."""
        from pathlib import Path
        from src.config.conversation_settings import CONVERSATION_SETTINGS
        from src.application.services.conversation.semantic_routing.configuration.prototype_catalog import (
            DEFAULT_PROTOTYPE_CATALOG,
        )
        from src.application.services.conversation.semantic_routing.infrastructure.embedding_provider import (
            LocalMiniLMEmbeddingProvider,
        )

        path = model_path or CONVERSATION_SETTINGS.semantic_model_path
        min_sim = min_similarity if min_similarity is not None else CONVERSATION_SETTINGS.min_similarity
        min_mar = min_margin if min_margin is not None else CONVERSATION_SETTINGS.min_margin
        dev = device or CONVERSATION_SETTINGS.device

        provider = LocalMiniLMEmbeddingProvider(path, device=dev)
        store = IntentPrototypeStore(provider, DEFAULT_PROTOTYPE_CATALOG)
        store.ensure_initialized()

        return cls(
            embedding_provider=provider,
            prototype_store=store,
            min_similarity=min_sim,
            min_margin=min_mar,
        )

    @property
    def min_similarity(self) -> float:
        return self._min_similarity

    @property
    def min_margin(self) -> float:
        return self._min_margin

    def classify(
        self,
        question: str,
        state: Optional[ConversationState] = None,
        *,
        has_history: bool = False,
    ) -> IntentClassificationResult:
        """Semantically classify the user message into a ConversationIntent."""
        norm_q = RequestNormalizer.normalize(question)
        if not norm_q:
            return IntentClassificationResult(
                intent=ConversationIntent.OUT_OF_SCOPE,
                confidence_score=0.0,
                margin=0.0,
                is_ambiguous=False,
                reason="Empty question provided.",
            )

        # 1. Encode query ONCE using the embedding provider
        query_vector = self._provider.encode_single(norm_q)

        # 2. Rank candidate intents using in-memory cosine similarity
        ranked = self._store.rank_intents(query_vector)
        if not ranked:
            return IntentClassificationResult(
                intent=ConversationIntent.NEW_DATABASE_QUERY,
                confidence_score=0.0,
                margin=0.0,
                is_ambiguous=True,
                reason="No prototype candidates available.",
            )

        best_intent, best_score, best_ex = ranked[0]
        second_intent = ranked[1][0] if len(ranked) > 1 else None
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = max(0.0, best_score - second_score)

        scores_dict = {item[0].value: round(item[1], 4) for item in ranked}

        logger.debug(
            "semantic_router.classified best=%s score=%.4f second=%s second_score=%.4f margin=%.4f query='%s'",
            best_intent.value,
            best_score,
            second_intent.value if second_intent else "NONE",
            second_score,
            margin,
            norm_q,
        )

        # 3. Explicit ambiguous intent detection
        if best_intent == ConversationIntent.AMBIGUOUS:
            return IntentClassificationResult(
                intent=ConversationIntent.AMBIGUOUS,
                confidence_score=best_score,
                margin=margin,
                is_ambiguous=True,
                second_intent=second_intent,
                second_score=second_score,
                matched_prototype=best_ex,
                reason="Matched ambiguous / anaphoric conversational prototype.",
                all_scores=scores_dict,
            )

        # 4. Context awareness evaluation
        has_context = has_history or (
            state is not None
            and (
                state.active_query_state is not None
                or state.last_successful_execution is not None
            )
        )

        # If follow-up is detected but there is NO conversation context:
        if best_intent.is_followup and not has_context:
            logger.info(
                "Follow-up intent '%s' detected but no active conversation context exists.",
                best_intent.value,
            )
            # Standalone question phrasing check: if the query resembles a standalone database query,
            # allow NEW_DATABASE_QUERY instead of failing, otherwise flag as ambiguous
            new_query_score = scores_dict.get(ConversationIntent.NEW_DATABASE_QUERY.value, 0.0)
            if new_query_score >= self._min_similarity:
                return IntentClassificationResult(
                    intent=ConversationIntent.NEW_DATABASE_QUERY,
                    confidence_score=new_query_score,
                    margin=margin,
                    is_ambiguous=False,
                    second_intent=best_intent,
                    second_score=best_score,
                    matched_prototype=best_ex,
                    reason="Context-independent fallback: no prior context for follow-up.",
                    all_scores=scores_dict,
                )
            else:
                return IntentClassificationResult(
                    intent=ConversationIntent.AMBIGUOUS,
                    confidence_score=best_score,
                    margin=margin,
                    is_ambiguous=True,
                    second_intent=second_intent,
                    second_score=second_score,
                    matched_prototype=best_ex,
                    reason="Follow-up intent detected without prior conversation context.",
                    all_scores=scores_dict,
                )

        # 5. Dual threshold gating: Confidence + Margin
        is_ambiguous = False
        reason = None

        if best_score < self._min_similarity:
            # Low confidence match
            is_ambiguous = True
            reason = f"Confidence score {best_score:.4f} is below minimum threshold {self._min_similarity:.4f}."
        elif margin < self._min_margin:
            # Competing intents with insufficient margin
            # Check if competing intents belong to different broad action categories
            if second_intent is not None:
                # If both are follow-up intents in an active conversation, use the highest scoring follow-up
                if has_context and best_intent.is_followup and second_intent.is_followup:
                    pass
                # If there is no active context, follow-up intents cannot compete with a new database query
                elif not has_context and second_intent.is_followup and best_intent == ConversationIntent.NEW_DATABASE_QUERY:
                    pass
                else:
                    is_ambiguous = True
                    reason = (
                        f"Ambiguous classification: margin between {best_intent.value} ({best_score:.4f}) "
                        f"and {second_intent.value} ({second_score:.4f}) is {margin:.4f} < {self._min_margin:.4f}."
                    )

        return IntentClassificationResult(
            intent=best_intent if not is_ambiguous else ConversationIntent.AMBIGUOUS,
            confidence_score=best_score,
            margin=margin,
            is_ambiguous=is_ambiguous,
            second_intent=second_intent,
            second_score=second_score,
            matched_prototype=best_ex,
            reason=reason,
            all_scores=scores_dict,
        )
