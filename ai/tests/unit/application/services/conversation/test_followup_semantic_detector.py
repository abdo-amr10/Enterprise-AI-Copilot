"""Unit tests for FollowupDetector with EntityRecognizer and SemanticTurnParser."""

from datetime import datetime
import pytest

from src.application.ports.llm_client import LLMClient
from src.application.services.conversation.extraction.entity_recognizer import get_entity_recognizer
from src.application.services.conversation.followup.followup_detector import FollowupDetector
from src.application.services.conversation.followup.models import (
    FollowupConfidence,
    FollowupType,
)
from src.application.services.conversation.semantic_routing.application.semantic_turn_parser import (
    SemanticTurnParser,
)
from src.application.services.conversation.state.conversation_state import (
    ConversationState,
    ExecutionRecord,
    SemanticQueryState,
)


@pytest.fixture
def state_with_context() -> ConversationState:
    state = ConversationState(conversation_id="conv_test_semantic")
    state.active_query_state = SemanticQueryState(raw_sql="SELECT * FROM customers")
    state.last_successful_execution = ExecutionRecord(
        sql="SELECT * FROM customers",
        status="Success",
        timestamp="2026-09-11T12:00:00Z",
        user_question="show all customers",
    )
    return state


class TestFollowupDetectorWordNumbers:
    """Verify limit detection works seamlessly with word numbers and ordinals."""

    @pytest.mark.parametrize(
        "query, expected_limit",
        [
            ("top five", "5"),
            ("top ten", "10"),
            ("extract top five", "5"),
            ("extract top twenty customers", "20"),
            ("make it top five", "5"),
            ("only top three", "3"),
            ("pull the first five records", "5"),
            ("first ten", "10"),
            ("extract 5", "5"),
            ("top 10", "10"),
        ],
    )
    def test_word_numbers_extracted_as_limit_change(
        self, state_with_context: ConversationState, query: str, expected_limit: str
    ) -> None:
        detector = FollowupDetector()
        res = detector.detect(query, state=state_with_context, has_history=True)
        assert res.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED
        assert res.operation_type == FollowupType.LIMIT_CHANGE
        assert res.target_value == expected_limit


class TestFollowupDetectorTemporalExpressions:
    """Verify temporal detection uses EntityRecognizer and handles general dates."""

    @pytest.mark.parametrize(
        "query, expected_type",
        [
            ("What about February?", FollowupType.TIME_CHANGE),
            ("What about in 2025?", FollowupType.TIME_CHANGE),
            ("What about last month?", FollowupType.TIME_CHANGE),
            ("What about yesterday?", FollowupType.TIME_CHANGE),
            ("change the date to 2026", FollowupType.TIME_CHANGE),
            ("change it to last year", FollowupType.TIME_CHANGE),
            ("What about in Chicago?", FollowupType.FILTER_CHANGE),
            ("What about VIP accounts?", FollowupType.FILTER_CHANGE),
        ],
    )
    def test_temporal_vs_filter_followup(
        self, state_with_context: ConversationState, query: str, expected_type: FollowupType
    ) -> None:
        detector = FollowupDetector()
        res = detector.detect(query, state=state_with_context, has_history=True)
        assert res.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED
        assert res.operation_type == expected_type


class TestFollowupDetectorWithSemanticTurnParser:
    """Verify primary path via SemanticTurnParser."""

    class MockParserLLM(LLMClient):
        def __init__(self, response_text: str) -> None:
            self._response = response_text

        def generate(self, request):
            from src.application.dto.llm.generation_response import GenerationResponse
            return GenerationResponse(text=self._response)

        async def generate_async(self, request):
            from src.application.dto.llm.generation_response import GenerationResponse
            return GenerationResponse(text=self._response)

    def test_semantic_parser_limit_change(self, state_with_context: ConversationState) -> None:
        mock_llm = self.MockParserLLM(
            '{"action": "MODIFY_QUERY", "limit": 7, "target_entity": null, "filters": [], "sort": null, "group_by": null, "confidence_score": 0.95}'
        )
        parser = SemanticTurnParser(llm_client=mock_llm)
        detector = FollowupDetector(semantic_parser=parser)

        res = detector.detect("Just the 7 highest ones", state=state_with_context, has_history=True)
        assert res.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED
        assert res.operation_type == FollowupType.LIMIT_CHANGE
        assert res.target_value == "7"

    def test_semantic_parser_filter_change(self, state_with_context: ConversationState) -> None:
        mock_llm = self.MockParserLLM(
            '{"action": "MODIFY_QUERY", "limit": null, "target_entity": null, "filters": [{"target": "status", "operator": "=", "value": "active"}], "sort": null, "group_by": null, "confidence_score": 0.92}'
        )
        parser = SemanticTurnParser(llm_client=mock_llm)
        detector = FollowupDetector(semantic_parser=parser)

        res = detector.detect("Only active status", state=state_with_context, has_history=True)
        assert res.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED
        assert res.operation_type == FollowupType.FILTER_CHANGE
        assert res.target_value == "active"

    def test_semantic_parser_reset_context(self, state_with_context: ConversationState) -> None:
        mock_llm = self.MockParserLLM(
            '{"action": "RESET", "limit": null, "target_entity": "show all products", "filters": [], "sort": null, "group_by": null, "confidence_score": 0.99}'
        )
        parser = SemanticTurnParser(llm_client=mock_llm)
        detector = FollowupDetector(semantic_parser=parser)

        res = detector.detect("Let us start over and show all products", state=state_with_context, has_history=True)
        assert res.confidence_level == FollowupConfidence.INDEPENDENT
        assert res.is_context_reset is True
        assert res.clean_question == "show all products"


class TestContinuationResolverDynamicEntities:
    """Verify ContinuationResolver uses EntityRecognizer for dynamic time and limits."""

    def test_continuation_time_change_dynamic(self, state_with_context: ConversationState) -> None:
        from src.application.services.conversation.continuation.continuation_resolver import (
            ContinuationResolver,
        )
        from src.application.services.conversation.followup.models import (
            FollowupDetectionResult,
            FollowupType,
        )

        resolver = ContinuationResolver()
        followup = FollowupDetectionResult(
            confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
            operation_type=FollowupType.TIME_CHANGE,
            target_value="2025",
        )

        res = resolver.resolve(
            "What about 2025?",
            state=state_with_context,
            followup=followup,
            prior_question="Show revenue for 2024",
        )
        assert res.is_resolved is True
        assert res.resolved_question == "Show revenue for 2025"
        assert res.updated_semantic_state.filters.get("time") == "2025"

    def test_continuation_limit_change_from_word_number(
        self, state_with_context: ConversationState
    ) -> None:
        from src.application.services.conversation.continuation.continuation_resolver import (
            ContinuationResolver,
        )
        from src.application.services.conversation.followup.models import (
            FollowupDetectionResult,
            FollowupType,
        )

        resolver = ContinuationResolver()
        followup = FollowupDetectionResult(
            confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
            operation_type=FollowupType.LIMIT_CHANGE,
            target_value="10",
        )

        res = resolver.resolve(
            "Make it top 10",
            state=state_with_context,
            followup=followup,
            prior_question="Show top five branches",
        )
        assert res.is_resolved is True
        assert res.resolved_question == "Show top 10 branches"
        assert res.updated_semantic_state.limit == 10


class TestResultResolverDynamicOrdinals:
    """Verify ResultResolver uses EntityRecognizer for dynamic ordinals."""

    def test_result_resolver_dynamic_ordinals(self) -> None:
        from src.application.services.conversation.result_resolution.models import (
            ResultResolutionStatus,
        )
        from src.application.services.conversation.result_resolution.result_resolver import (
            ResultResolver,
        )
        from src.application.services.conversation.state.conversation_state import (
            ResultMetadata,
        )

        resolver = ResultResolver()
        meta = ResultMetadata(
            columns=("CustomerName", "City", "Balance"),
            row_count=5,
            sample_rows=(
                ("Alice Corp", "New York", 1000),
                ("Bob Ltd", "London", 2000),
                ("Charlie Inc", "Tokyo", 3000),
                ("Delta LLC", "Paris", 4000),
                ("Echo Co", "Berlin", 5000),
            ),
        )

        # "second" via EntityRecognizer
        res2 = resolver.resolve("What was the second row?", meta)
        assert res2.status == ResultResolutionStatus.ANSWERABLE
        assert "Bob Ltd" in res2.answer

        # "fourth" via EntityRecognizer
        res4 = resolver.resolve("Who is the fourth one?", meta)
        assert res4.status == ResultResolutionStatus.ANSWERABLE
        assert "Delta LLC" in res4.answer

        # "5th" via EntityRecognizer
        res5 = resolver.resolve("What is the 5th result?", meta)
        assert res5.status == ResultResolutionStatus.ANSWERABLE
        assert "Echo Co" in res5.answer

