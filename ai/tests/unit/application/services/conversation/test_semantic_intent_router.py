"""Comprehensive test suite for the Semantic Intent Router using local all-MiniLM-L6-v2."""

from __future__ import annotations

from pathlib import Path
import time
import pytest

from src.application.services.conversation.semantic_routing.application.semantic_intent_router import (
    SemanticIntentRouter,
)
from src.application.services.conversation.semantic_routing.configuration.prototype_catalog import (
    DEFAULT_PROTOTYPE_CATALOG,
)
from src.application.services.conversation.semantic_routing.domain.intent import (
    ConversationIntent,
)
from src.application.services.conversation.semantic_routing.infrastructure.embedding_provider import (
    LocalMiniLMEmbeddingProvider,
)
from src.application.services.conversation.semantic_routing.infrastructure.intent_prototype_store import (
    IntentPrototypeStore,
)
from src.application.services.conversation.state.conversation_state import (
    ConversationState,
    SemanticQueryState,
)

_MODEL_PATH = (
    Path(__file__).resolve().parents[5]
    / "models"
    / "embeddings"
    / "all-MiniLM-L6-v2"
)



@pytest.fixture(scope="module")
def semantic_router() -> SemanticIntentRouter:
    provider = LocalMiniLMEmbeddingProvider(_MODEL_PATH)
    store = IntentPrototypeStore(provider, DEFAULT_PROTOTYPE_CATALOG)
    store.ensure_initialized()
    return SemanticIntentRouter(
        embedding_provider=provider,
        prototype_store=store,
        min_similarity=0.35,
        min_margin=0.03,
    )


@pytest.fixture
def active_state() -> ConversationState:
    return ConversationState(
        conversation_id="test_conv",
        active_query_state=SemanticQueryState(
            entities=("customers",),
            metrics=("revenue",),
        ),
    )


# ==============================================================================
# 1. Known Prototype Classification Tests
# ==============================================================================
class TestKnownPrototypes:
    @pytest.mark.parametrize(
        ("question", "expected_intent"),
        [
            ("What can you do?", ConversationIntent.CAPABILITY),
            ("What are you capable of?", ConversationIntent.CAPABILITY),
            ("Show only five", ConversationIntent.LIMIT_CHANGE),
            ("Give me the top five", ConversationIntent.LIMIT_CHANGE),
            ("Sort them by balance descending", ConversationIntent.SORT_CHANGE),
            ("Group it by region", ConversationIntent.GROUP_BY_CHANGE),
            ("Only Chicago", ConversationIntent.FILTER_CHANGE),
            ("No, I meant Chicago", ConversationIntent.CORRECTION),
            ("Which of them has the highest balance?", ConversationIntent.PRONOUN_REFERENCE),
            ("New question", ConversationIntent.RESET_CONTEXT),
            ("Write a poem or a creative story", ConversationIntent.OUT_OF_SCOPE),
            ("Show total sales by country", ConversationIntent.NEW_DATABASE_QUERY),
        ],
    )
    def test_known_prototypes_classify_correctly(
        self, semantic_router: SemanticIntentRouter, active_state: ConversationState, question: str, expected_intent: ConversationIntent
    ):
        result = semantic_router.classify(question, state=active_state, has_history=True)
        assert result.intent == expected_intent
        assert result.confidence_score >= 0.85
        assert not result.is_ambiguous


# ==============================================================================
# 2. Unseen Paraphrase Generalization Tests (Crucial: none of these are in prototypes!)
# ==============================================================================
class TestUnseenParaphraseGeneralization:
    """Tests unseen phrases that are NOT present in DEFAULT_PROTOTYPE_CATALOG."""

    @pytest.mark.parametrize(
        ("unseen_question", "expected_intent"),
        [
            # Capability unseen variations
            ("What kinds of tasks can you handle?", ConversationIntent.CAPABILITY),
            ("What are you actually able to help with?", ConversationIntent.CAPABILITY),
            ("What sort of things can I ask you to do?", ConversationIntent.CAPABILITY),
            ("Tell me about your core abilities", ConversationIntent.CAPABILITY),
            # Limit unseen variations
            ("I only need the first seven.", ConversationIntent.LIMIT_CHANGE),
            ("Just show 4 results", ConversationIntent.LIMIT_CHANGE),
            ("Keep only the highest 8 records", ConversationIntent.LIMIT_CHANGE),
            ("Cap the output to twelve rows", ConversationIntent.LIMIT_CHANGE),
            # Sort unseen variations
            ("Arrange them by profit ascending", ConversationIntent.SORT_CHANGE),
            ("Order by balance from highest to lowest", ConversationIntent.SORT_CHANGE),
            ("Rank the output by total transactions", ConversationIntent.SORT_CHANGE),
            # Group by unseen variations
            ("Separate them by branch", ConversationIntent.GROUP_BY_CHANGE),
            ("Group according to customer type", ConversationIntent.GROUP_BY_CHANGE),
            ("Partition the data by year", ConversationIntent.GROUP_BY_CHANGE),
            # Filter unseen variations
            ("Filter by active customers only", ConversationIntent.FILTER_CHANGE),
            ("What about in Miami?", ConversationIntent.FILTER_CHANGE),
            ("Show the identical report for New York", ConversationIntent.FILTER_CHANGE),
            # Correction unseen variations
            ("Actually, make that below 500", ConversationIntent.CORRECTION),
            ("No, change that to 2024 instead", ConversationIntent.CORRECTION),
            ("Actually, greater than 1000", ConversationIntent.CORRECTION),
            # Pronoun reference unseen variations
            ("Which one has the highest credit rating?", ConversationIntent.PRONOUN_REFERENCE),
            ("Who among those has the lowest balance?", ConversationIntent.PRONOUN_REFERENCE),
            # Reset unseen variations
            ("Start completely fresh with another query", ConversationIntent.RESET_CONTEXT),
            ("Wipe the current conversation context", ConversationIntent.RESET_CONTEXT),
            # Out of scope unseen variations
            ("Compose a funny poem about cats", ConversationIntent.OUT_OF_SCOPE),
            ("What is the temperature in Seattle right now?", ConversationIntent.OUT_OF_SCOPE),
            ("Who won the FIFA World Cup in 1994?", ConversationIntent.OUT_OF_SCOPE),
            ("Do you have personal feelings or consciousness?", ConversationIntent.OUT_OF_SCOPE),
            # New database query unseen variations
            ("List all customer transactions exceeding ten thousand dollars", ConversationIntent.NEW_DATABASE_QUERY),
            ("How many accounts were opened in the second quarter?", ConversationIntent.NEW_DATABASE_QUERY),
            ("Find all suppliers operating in the eastern territory", ConversationIntent.NEW_DATABASE_QUERY),
        ],
    )
    def test_unseen_paraphrases_classify_correctly(
        self, semantic_router: SemanticIntentRouter, active_state: ConversationState, unseen_question: str, expected_intent: ConversationIntent
    ):
        result = semantic_router.classify(unseen_question, state=active_state, has_history=True)
        assert result.intent == expected_intent, (
            f"Failed on unseen phrase '{unseen_question}'. "
            f"Got {result.intent.value} (score={result.confidence_score:.4f}, margin={result.margin:.4f}, closest={result.matched_prototype}), "
            f"expected {expected_intent.value}. All scores: {result.all_scores}"
        )
        assert result.confidence_score >= semantic_router.min_similarity


# ==============================================================================
# 3. Short Conversational Messages
# ==============================================================================
class TestShortConversationalMessages:
    def test_short_limit(self, semantic_router: SemanticIntentRouter, active_state: ConversationState):
        res = semantic_router.classify("Top five.", state=active_state, has_history=True)
        assert res.intent == ConversationIntent.LIMIT_CHANGE

    def test_short_filter(self, semantic_router: SemanticIntentRouter, active_state: ConversationState):
        res = semantic_router.classify("And Chicago?", state=active_state, has_history=True)
        assert res.intent == ConversationIntent.FILTER_CHANGE

    def test_short_sort(self, semantic_router: SemanticIntentRouter, active_state: ConversationState):
        res = semantic_router.classify("Sort by total", state=active_state, has_history=True)
        assert res.intent == ConversationIntent.SORT_CHANGE


# ==============================================================================
# 4. Context-Awareness & Safe Fallbacks
# ==============================================================================
class TestContextAwareness:
    def test_followup_without_history_falls_back_safely(self, semantic_router: SemanticIntentRouter):
        """When a follow-up is asked cold without history, it must NOT corrupt state or assume history."""
        res = semantic_router.classify("Top five.", state=None, has_history=False)
        # Without context, it cannot be an active continuation
        assert res.is_ambiguous or res.intent == ConversationIntent.NEW_DATABASE_QUERY

    def test_empty_query_returns_out_of_scope(self, semantic_router: SemanticIntentRouter):
        res = semantic_router.classify("   ")
        assert res.intent == ConversationIntent.OUT_OF_SCOPE


# ==============================================================================
# 5. Ambiguous and Adversarial Cases
# ==============================================================================
class TestAmbiguousAndAdversarialCases:
    @pytest.mark.parametrize(
        "ambiguous_question",
        [
            "What about it?",
            "How about that?",
            "Those?",
            "Do that again.",
        ],
    )
    def test_anaphoric_ambiguity_flagged(
        self, semantic_router: SemanticIntentRouter, active_state: ConversationState, ambiguous_question: str
    ):
        res = semantic_router.classify(ambiguous_question, state=active_state, has_history=True)
        assert res.intent == ConversationIntent.AMBIGUOUS
        assert res.is_ambiguous is True


# ==============================================================================
# 6. Latency & Performance Benchmark
# ==============================================================================
class TestLatencyBenchmark:
    def test_single_inference_p50_under_35ms(self, semantic_router: SemanticIntentRouter, active_state: ConversationState):
        phrases = [
            "Show total sales by country",
            "What kinds of tasks can you handle?",
            "I only need the first seven.",
            "Sort them by balance descending",
            "Separate them by branch",
            "No, I meant Chicago",
            "Write a poem about computers",
            "What about Alexandria?",
            "New question",
            "Which of them has the highest balance?",
        ]
        # Warm up
        semantic_router.classify("warm up", state=active_state, has_history=True)

        latencies = []
        for p in phrases * 5:  # 50 iterations
            t0 = time.perf_counter()
            semantic_router.classify(p, state=active_state, has_history=True)
            latencies.append((time.perf_counter() - t0) * 1000)

        import numpy as np
        p50 = float(np.percentile(latencies, 50))
        p95 = float(np.percentile(latencies, 95))
        p99 = float(np.percentile(latencies, 99))

        print(f"\nRouter Latency: P50={p50:.2f}ms, P95={p95:.2f}ms, P99={p99:.2f}ms")
        assert p50 < 35.0, f"Expected P50 < 35ms, got {p50:.2f}ms"
