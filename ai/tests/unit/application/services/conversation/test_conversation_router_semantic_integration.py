"""End-to-end integration tests for ConversationRouter with SemanticIntentRouter."""

from __future__ import annotations

import pytest

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.backend.copilot.text_to_sql_runtime_response import (
    TextToSQLRuntimeResponse,
)
from src.application.services.conversation.router.conversation_router import (
    ConversationRouter,
)
from src.application.services.conversation.router.routing_decision import (
    ConversationRoute,
)
from src.application.services.conversation.semantic_routing.domain.intent import (
    ConversationIntent,
)


class MockCopilotExecutor:
    """Mock executor tracking calls and providing deterministic SQL."""

    def __init__(self) -> None:
        self.invocations: list[CopilotAskRequest] = []

    def run(self, request: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        self.invocations.append(request)
        return TextToSQLRuntimeResponse.success(
            f"SELECT * FROM mock_table WHERE query = '{request.question}';"
        )


@pytest.fixture
def router() -> ConversationRouter:
    return ConversationRouter()


@pytest.fixture
def executor() -> MockCopilotExecutor:
    return MockCopilotExecutor()


# ==============================================================================
# 1. Capability Direct Routing Tests (Zero SQL, Zero LLM)
# ==============================================================================
class TestCapabilityRouting:
    @pytest.mark.parametrize(
        "phrase",
        [
            "What can you do?",
            "What kinds of tasks can you handle?",
            "Explain your features and capabilities",
            "What are you actually able to help with?",
            "Tell me about your core abilities",
        ],
    )
    def test_capability_routed_directly_without_sql(
        self, router: ConversationRouter, executor: MockCopilotExecutor, phrase: str
    ):
        decision = router.route(
            phrase,
            conversation_id="conv_cap",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=executor.run,
        )

        assert decision.route == ConversationRoute.CAPABILITY
        assert decision.is_success is True
        assert decision.generated_sql is None
        assert decision.direct_answer is not None
        assert "Copilot" in decision.direct_answer
        assert decision.semantic_intent == ConversationIntent.CAPABILITY.value
        assert decision.semantic_confidence is not None
        assert len(executor.invocations) == 0  # Text-to-SQL never called!

        obs = decision.to_observability_dict()
        assert obs["conversation_route"] == "CAPABILITY"
        assert obs["semantic_intent"] == "CAPABILITY"
        assert obs["semantic_confidence"] > 0.35


# ==============================================================================
# 2. Out-of-Scope Early Safe Rejection Tests
# ==============================================================================
class TestOutOfScopeRouting:
    @pytest.mark.parametrize(
        "phrase",
        [
            "Compose a funny poem about cats",
            "What is the temperature in Seattle right now?",
            "Who won the FIFA World Cup in 1994?",
            "Do you have personal feelings or consciousness?",
        ],
    )
    def test_out_of_scope_safely_rejected(
        self, router: ConversationRouter, executor: MockCopilotExecutor, phrase: str
    ):
        decision = router.route(
            phrase,
            conversation_id="conv_oos",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=executor.run,
        )

        assert decision.route == ConversationRoute.UNSUPPORTED
        assert decision.is_success is False
        assert decision.generated_sql is None
        assert decision.error_message is not None
        assert "I can only" in decision.error_message
        assert len(executor.invocations) == 0  # Text-to-SQL never called!

        obs = decision.to_observability_dict()
        assert obs["conversation_route"] == "UNSUPPORTED"
        assert obs["semantic_intent"] == "OUT_OF_SCOPE"


# ==============================================================================
# 3. Multi-Turn Follow-Up with Unseen Phrasings
# ==============================================================================
class TestMultiTurnFollowupUnseenPhrasings:
    def test_unseen_limit_followup(
        self, router: ConversationRouter, executor: MockCopilotExecutor
    ):
        # Turn 1: Initial query
        t1 = router.route(
            "Show customers in Cairo",
            conversation_id="conv_followup_1",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=executor.run,
        )
        assert t1.route == ConversationRoute.NEW_DATABASE_QUERY
        assert len(executor.invocations) == 1

        # Turn 2: Unseen limit phrasing ("I only need the first seven.")
        t2 = router.route(
            "I only need the first seven.",
            conversation_id="conv_followup_1",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show customers in Cairo"},),
            executor=executor.run,
        )
        assert t2.route == ConversationRoute.FOLLOW_UP_QUERY
        assert t2.is_success is True
        assert t2.semantic_intent == ConversationIntent.LIMIT_CHANGE.value
        assert "7" in t2.resolved_question or "seven" in t2.resolved_question.lower()
        assert len(executor.invocations) == 2

    def test_unseen_sort_followup(
        self, router: ConversationRouter, executor: MockCopilotExecutor
    ):
        # Turn 1
        router.route(
            "Show customers in Cairo",
            conversation_id="conv_followup_2",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=executor.run,
        )
        # Turn 2: Unseen sort phrasing
        t2 = router.route(
            "Arrange them by profit ascending",
            conversation_id="conv_followup_2",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show customers in Cairo"},),
            executor=executor.run,
        )
        assert t2.route == ConversationRoute.FOLLOW_UP_QUERY
        assert t2.is_success is True
        assert t2.semantic_intent == ConversationIntent.SORT_CHANGE.value
        assert "profit" in t2.resolved_question.lower()

    def test_unseen_group_by_followup(
        self, router: ConversationRouter, executor: MockCopilotExecutor
    ):
        # Turn 1
        router.route(
            "Show customers in Cairo",
            conversation_id="conv_followup_3",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=executor.run,
        )
        # Turn 2: Unseen group by phrasing
        t2 = router.route(
            "Separate them by branch",
            conversation_id="conv_followup_3",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show customers in Cairo"},),
            executor=executor.run,
        )
        assert t2.route == ConversationRoute.FOLLOW_UP_QUERY
        assert t2.is_success is True
        assert t2.semantic_intent == ConversationIntent.GROUP_BY_CHANGE.value
        assert "branch" in t2.resolved_question.lower()


# ==============================================================================
# 4. Fallback Safety When Semantic Router is Explicitly Disabled
# ==============================================================================
class TestDisabledSemanticRouterFallback:
    def test_router_falls_back_when_semantic_router_is_none(
        self, executor: MockCopilotExecutor
    ):
        router_no_semantic = ConversationRouter(semantic_router=None)
        assert router_no_semantic.semantic_router is None

        # Turn 1: Normal query
        t1 = router_no_semantic.route(
            "Show all merchants in Alexandria",
            conversation_id="conv_fallback",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=executor.run,
        )
        assert t1.route == ConversationRoute.NEW_DATABASE_QUERY
        assert t1.semantic_intent is None

        # Turn 2: Deterministic follow-up (regex-based)
        t2 = router_no_semantic.route(
            "Top 5",
            conversation_id="conv_fallback",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show all merchants in Alexandria"},),
            executor=executor.run,
        )
        assert t2.route == ConversationRoute.FOLLOW_UP_QUERY
        assert t2.is_success is True
        assert t2.semantic_intent is None
