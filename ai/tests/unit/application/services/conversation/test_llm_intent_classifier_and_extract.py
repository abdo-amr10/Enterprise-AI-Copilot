"""Tests for LLMIntentClassifier and 'extract' follow-up handling."""

from __future__ import annotations

import pytest

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.backend.copilot.text_to_sql_runtime_response import (
    TextToSQLRuntimeResponse,
)
from src.application.services.conversation.continuation.continuation_resolver import (
    ContinuationResolver,
)
from src.application.services.conversation.followup.followup_detector import (
    FollowupDetector,
)
from src.application.services.conversation.followup.models import (
    FollowupConfidence,
    FollowupType,
)
from src.application.services.conversation.router.conversation_router import (
    ConversationRoute,
    ConversationRouter,
)
from src.application.services.conversation.semantic_routing.application.llm_intent_classifier import (
    LLMIntentClassifier,
)
from src.application.services.conversation.semantic_routing.domain.classification_result import (
    IntentClassificationResult,
)
from src.application.services.conversation.semantic_routing.domain.intent import (
    ConversationIntent,
)
from src.application.services.conversation.state.conversation_state import (
    ConversationState,
    ExecutionRecord,
    SemanticQueryState,
)
from tests.unit.application.services.conversation.fake_llm_client import (
    FailingLLMClient,
    FakeSequentialLLMClient,
)


class TestFollowupDetectorExtractPatterns:
    @pytest.fixture
    def detector(self) -> FollowupDetector:
        return FollowupDetector()

    @pytest.fixture
    def state_with_history(self) -> ConversationState:
        state = ConversationState(conversation_id="c_test")
        state.active_query_state = SemanticQueryState(raw_sql="SELECT * FROM customers")
        state.last_successful_execution = ExecutionRecord(
            sql="SELECT * FROM customers",
            status="Success",
            timestamp="2026-09-10T12:00:00Z",
            user_question="show all customers",
        )
        return state

    @pytest.mark.parametrize(
        "query, expected_limit",
        [
            ("extract top 5", "5"),
            ("extract top 5 from result", "5"),
            ("extract top 5 from the result", "5"),
            ("extract top 10 customers", "10"),
            ("extract 5", "5"),
            ("pull top 10", "10"),
            ("pull the first 10 records", "10"),
            ("top 5", "5"),
            ("make it top 5", "5"),
            ("only top 5", "5"),
        ],
    )
    def test_extract_queries_detected_as_limit_change(
        self, detector: FollowupDetector, state_with_history: ConversationState, query: str, expected_limit: str
    ) -> None:
        result = detector.detect(query, state=state_with_history, has_history=True)
        assert result.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED
        assert result.operation_type == FollowupType.LIMIT_CHANGE
        assert result.target_value == expected_limit


class TestContinuationResolverExtract:
    def test_continuation_cleans_base_question(self) -> None:
        resolver = ContinuationResolver()
        detector = FollowupDetector()
        state = ConversationState(conversation_id="c_test")
        state.active_query_state = SemanticQueryState(raw_sql="SELECT * FROM customers")

        detection = detector.detect("extract top 5", state=state, has_history=True)
        res = resolver.resolve("extract top 5", state, detection, prior_question="show all customers")

        assert res.is_resolved is True
        assert res.resolved_question == "Show top 5 customers"
        assert res.updated_semantic_state.limit == 5


class TestLLMIntentClassifier:
    def test_classify_limit_change(self) -> None:
        fake_llm = FakeSequentialLLMClient(["LIMIT_CHANGE"])
        classifier = LLMIntentClassifier(fake_llm)

        result = classifier.classify("extract top 5 from the previous table", has_history=True)
        assert result.intent == ConversationIntent.LIMIT_CHANGE
        assert result.is_ambiguous is False
        assert result.confidence_score == 0.85

    def test_classify_sort_change(self) -> None:
        fake_llm = FakeSequentialLLMClient(["SORT_CHANGE"])
        classifier = LLMIntentClassifier(fake_llm)

        result = classifier.classify("order them by balance descending", has_history=True)
        assert result.intent == ConversationIntent.SORT_CHANGE
        assert result.is_ambiguous is False

    def test_classify_with_extra_text(self) -> None:
        fake_llm = FakeSequentialLLMClient(["The intent is FILTER_CHANGE."])
        classifier = LLMIntentClassifier(fake_llm)

        result = classifier.classify("only in Cairo branch", has_history=True)
        assert result.intent == ConversationIntent.FILTER_CHANGE
        assert result.is_ambiguous is False

    def test_classify_unrecognized_returns_ambiguous(self) -> None:
        fake_llm = FakeSequentialLLMClient(["I have no idea what the user wants"])
        classifier = LLMIntentClassifier(fake_llm)

        result = classifier.classify("something completely strange", has_history=True)
        assert result.intent == ConversationIntent.AMBIGUOUS
        assert result.is_ambiguous is True

    def test_failing_llm_client_returns_ambiguous_gracefully(self) -> None:
        classifier = LLMIntentClassifier(FailingLLMClient())

        result = classifier.classify("any question", has_history=True)
        assert result.intent == ConversationIntent.AMBIGUOUS
        assert result.is_ambiguous is True


class DummyAmbiguousSemanticRouter:
    """Always returns AMBIGUOUS to test LLM fallback in ConversationRouter."""

    def classify(self, question: str, state=None, has_history=False):
        return IntentClassificationResult(
            intent=ConversationIntent.AMBIGUOUS,
            confidence_score=0.30,
            margin=0.01,
            is_ambiguous=True,
            reason="Simulated ambiguous classification",
        )


class TestConversationRouterLLMFallback:
    def test_router_uses_llm_fallback_when_ambiguous(self) -> None:
        fake_llm = FakeSequentialLLMClient(["LIMIT_CHANGE"])
        llm_classifier = LLMIntentClassifier(fake_llm)

        router = ConversationRouter(
            semantic_router=DummyAmbiguousSemanticRouter(),
            llm_intent_classifier=llm_classifier,
        )

        def dummy_executor(ask_req: CopilotAskRequest) -> TextToSQLRuntimeResponse:
            return TextToSQLRuntimeResponse(
                status="Success",
                sql=f"SELECT * FROM customers LIMIT 5 -- resolved: {ask_req.question}",
            )

        raw_convo = (
            {
                "role": "turn",
                "user_question": "show all customers",
                "generated_sql": "SELECT * FROM customers",
                "execution_status": "Success",
            },
        )

        decision = router.route(
            question="narrow it down to 5",
            raw_conversation=raw_convo,
            conversation_id="conv_fallback_test",
            executor=dummy_executor,
        )

        assert decision.is_success is True
        assert decision.route == ConversationRoute.FOLLOW_UP_QUERY
        assert decision.llm_used_by_conversation_layer is True
        assert "LIMIT 5" in (decision.generated_sql or "")


class TestResultResolverSummaryReplay:
    def test_summary_replay_handles_what_the_summary_about_result(self) -> None:
        from src.application.services.conversation.result_resolution.result_resolver import (
            ResultResolver,
        )
        from src.application.services.conversation.state.conversation_state import (
            ResultMetadata,
        )

        resolver = ResultResolver()
        meta = ResultMetadata(
            columns=("id", "name"),
            row_count=150,
            summary="The data shows there are 150 customers in the system.",
        )

        queries = [
            "what the summay about result",
            "what is the summary of the result",
            "summary about result",
            "what the summary of the query",
            "summarize the result",
        ]

        for q in queries:
            outcome = resolver.resolve(q, meta, summary=meta.summary)
            assert outcome.status.value == "ANSWERABLE", f"Failed for query: {q}"
            assert outcome.answer == "The data shows there are 150 customers in the system."

