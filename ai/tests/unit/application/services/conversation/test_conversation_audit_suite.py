"""Comprehensive Audit and Regression Test Suite for Conversation Layer.

Covers:
Category A - Exact Replay & Cache Scoping
Category B - Result-Aware Resolution & Zero-Hallucination Boundaries
Category C - Follow-up Detection & Continuation (Replacement vs Addition)
Category D - Independent Queries & Complete Questions
Category E - Context Contamination Verification (WHERE, TOP, ORDER BY, GROUP BY)
Category F - Security Scope Isolation & RLS Boundary Invariants
Category G - Multi-Turn, Context Branching, and Context Reset
"""

from __future__ import annotations

from typing import Any, Optional
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
from src.application.services.conversation.replay.replay_manager import (
    ExactReplayManager,
)
from src.application.services.conversation.result_resolution.models import (
    ResultResolutionStatus,
)
from src.application.services.conversation.result_resolution.result_resolver import (
    ResultResolver,
)
from src.application.services.conversation.router.conversation_router import (
    ConversationRouter,
)
from src.application.services.conversation.router.routing_decision import (
    ConversationRoute,
)
from src.application.services.conversation.state.conversation_state import (
    ResultMetadata,
    SemanticQueryState,
)
from src.application.services.conversation.state.state_manager import (
    ConversationStateManager,
)


class MockExecutor:
    """Mock Text-to-SQL executor tracking invocations and input requests."""

    def __init__(self) -> None:
        self.invocations: list[CopilotAskRequest] = []
        self.next_sql: str = "SELECT * FROM MockTable"

    def run(self, request: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        self.invocations.append(request)
        return TextToSQLRuntimeResponse.success(self.next_sql)


@pytest.fixture
def mock_executor() -> MockExecutor:
    return MockExecutor()


@pytest.fixture
def conversation_router() -> ConversationRouter:
    return ConversationRouter()


# ==============================================================================
# Category A — Exact Replay & Cache Scoping
# ==============================================================================
class TestCategoryAExactReplay:
    """AC-01, AC-11, AC-12: Exact replay under valid context, rejected on scope change."""

    def test_replay_exact_same_question(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        # 1st execution
        resp1 = conversation_router.route(
            "Show customers with credit score above 700.",
            conversation_id="conv_a1",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        assert resp1.route == ConversationRoute.NEW_DATABASE_QUERY
        assert len(mock_executor.invocations) == 1

        # 2nd execution (Exact match)
        resp2 = conversation_router.route(
            "Show customers with credit score above 700.",
            conversation_id="conv_a1",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        assert resp2.route == ConversationRoute.EXACT_REPLAY
        assert resp2.cache_hit is True
        assert len(mock_executor.invocations) == 1  # No Text-to-SQL called

    def test_replay_normalized_equivalent_whitespace_case(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        conversation_router.route(
            "Show customers with credit score above 700.",
            conversation_id="conv_a2",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        resp2 = conversation_router.route(
            "  show   customers with   credit score above 700.  ",
            conversation_id="conv_a2",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        assert resp2.route == ConversationRoute.EXACT_REPLAY

    def test_replay_not_triggered_for_changed_predicate(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        conversation_router.route(
            "Show customers with credit score above 700.",
            conversation_id="conv_a3",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        # Predicate changed from 700 to 750
        resp2 = conversation_router.route(
            "Show customers with credit score above 750.",
            conversation_id="conv_a3",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        assert resp2.route != ConversationRoute.EXACT_REPLAY
        assert len(mock_executor.invocations) == 2

    def test_replay_rejected_across_branch_security_scope(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        # Branch 1 executes
        conversation_router.route(
            "Show customers with credit score above 700.",
            conversation_id="conv_a4",
            branch_id="branch_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        # Branch 2 requests same question
        resp_branch2 = conversation_router.route(
            "Show customers with credit score above 700.",
            conversation_id="conv_a4",
            branch_id="branch_2",
            user_id="user_1",
            executor=mock_executor.run,
        )
        # Must NOT replay branch_1's result/sql across branch security boundary
        assert resp_branch2.route != ConversationRoute.EXACT_REPLAY
        assert len(mock_executor.invocations) == 2

    def test_replay_rejected_across_user_security_scope(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        conversation_router.route(
            "Show customers with credit score above 700.",
            conversation_id="conv_a5",
            tenant_id="tenant_1",
            user_id="user_alice",
            executor=mock_executor.run,
        )
        resp_bob = conversation_router.route(
            "Show customers with credit score above 700.",
            conversation_id="conv_a5",
            tenant_id="tenant_1",
            user_id="user_bob",
            executor=mock_executor.run,
        )
        assert resp_bob.route != ConversationRoute.EXACT_REPLAY


# ==============================================================================
# Category B — Result-Aware Resolution & Zero-Hallucination Boundaries
# ==============================================================================
class TestCategoryBResultResolution:
    """AC-02, AC-13, AC-17: Direct result answers without SQL/LLM; strict zero hallucination."""

    def test_count_resolution_from_result(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        # Result metadata has 5 rows
        last_result = {
            "columns": ["customer_id", "customer_name", "amount"],
            "rows": [[1, "Ahmed", 500], [2, "Sara", 600], [3, "Mona", 700], [4, "Ali", 800], [5, "Omar", 900]],
            "rowCount": 5,
        }
        resp = conversation_router.route(
            "How many are there?",
            conversation_id="conv_b1",
            tenant_id="tenant_1",
            user_id="user_1",
            last_result_metadata=last_result,
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.RESULT_ANSWER
        assert "5 rows" in resp.text_summary
        assert len(mock_executor.invocations) == 0  # Zero SQL / Zero LLM

    def test_count_entity_mismatch_falls_through(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        # Previous result was customers, new question asks about branches
        last_result = {
            "columns": ["customer_id", "customer_name"],
            "rows": [[1, "Ahmed"], [2, "Sara"]],
            "rowCount": 2,
        }
        resp = conversation_router.route(
            "How many branches are in Cairo?",
            conversation_id="conv_b2",
            tenant_id="tenant_1",
            user_id="user_1",
            last_result_metadata=last_result,
            executor=mock_executor.run,
        )
        # Must NOT answer "There are 2 rows in the previous result."
        assert resp.route != ConversationRoute.RESULT_ANSWER
        assert resp.route == ConversationRoute.NEW_DATABASE_QUERY

    def test_extreme_resolution_with_present_metric(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        last_result = {
            "columns": ["customer_name", "balance"],
            "rows": [["Ahmed", 1000], ["Sara", 5000], ["Ali", 2500]],
            "rowCount": 3,
        }
        resp = conversation_router.route(
            "Which one has the highest balance?",
            conversation_id="conv_b3",
            tenant_id="tenant_1",
            user_id="user_1",
            last_result_metadata=last_result,
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.RESULT_ANSWER
        assert "Sara has the highest balance (5000" in resp.text_summary
        assert len(mock_executor.invocations) == 0

    def test_extreme_resolution_zero_hallucination_when_metric_absent(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        # Result columns do NOT have balance, only customer_id and customer_name
        last_result = {
            "columns": ["customer_id", "customer_name"],
            "rows": [[101, "Ahmed"], [102, "Sara"], [103, "Ali"]],
            "rowCount": 3,
        }
        resp = conversation_router.route(
            "Which one has the highest balance?",
            conversation_id="conv_b4",
            tenant_id="tenant_1",
            user_id="user_1",
            last_result_metadata=last_result,
            executor=mock_executor.run,
        )
        # Must NOT hallucinate by picking customer_id! Must generate a database query!
        assert resp.route != ConversationRoute.RESULT_ANSWER
        assert len(mock_executor.invocations) == 1

    def test_ordinal_does_not_hijack_limit_query(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        last_result = {
            "columns": ["customer_id", "customer_name"],
            "rows": [[1, "Ahmed"], [2, "Sara"]],
            "rowCount": 2,
        }
        # "First 10 customers" must NOT be answered as "Number 1 is Ahmed"
        resp = conversation_router.route(
            "First 10 customers",
            conversation_id="conv_b5",
            tenant_id="tenant_1",
            user_id="user_1",
            last_result_metadata=last_result,
            executor=mock_executor.run,
        )
        assert resp.route != ConversationRoute.RESULT_ANSWER


# ==============================================================================
# Category C — Follow-Up Detection & Continuation
# ==============================================================================
class TestCategoryCFollowUpContinuation:
    """AC-03, AC-10, AC-16: True follow-ups, entity substitution, and filter replacement."""

    def test_scope_substitution_followup(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        # A: Show sales for Cairo branch.
        conversation_router.route(
            "Show sales for Cairo branch.",
            conversation_id="conv_c1",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        # B: What about Alexandria?
        resp_b = conversation_router.route(
            "What about Alexandria?",
            conversation_id="conv_c1",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show sales for Cairo branch."},),
            executor=mock_executor.run,
        )
        assert resp_b.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "Alexandria" in resp_b.resolved_question
        assert "Cairo" not in resp_b.resolved_question  # Cairo replaced, not duplicated!

    def test_pronoun_referential_followup(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        # A: Show the top 10 customers by transaction amount.
        conversation_router.route(
            "Show the top 10 customers by transaction amount.",
            conversation_id="conv_c2",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        # B: Sort them by credit score.
        resp_b = conversation_router.route(
            "Sort them by credit score.",
            conversation_id="conv_c2",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show the top 10 customers by transaction amount."},),
            executor=mock_executor.run,
        )
        assert resp_b.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "credit score" in resp_b.resolved_question.lower()

    def test_filter_replacement_with_actually_make_that(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        # A: Show transactions in 2025.
        conversation_router.route(
            "Show transactions in 2025.",
            conversation_id="conv_c3",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        # B: Actually, make that 2026.
        resp_b = conversation_router.route(
            "Actually, make that 2026.",
            conversation_id="conv_c3",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show transactions in 2025."},),
            executor=mock_executor.run,
        )
        assert resp_b.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "2026" in resp_b.resolved_question
        assert "2025" not in resp_b.resolved_question

    def test_filter_replacement_with_negation(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        # A: Show customers in Cairo.
        conversation_router.route(
            "Show customers in Cairo.",
            conversation_id="conv_c4",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        # B: Not Cairo - show Alexandria instead.
        resp_b = conversation_router.route(
            "Not Cairo - show Alexandria instead.",
            conversation_id="conv_c4",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show customers in Cairo."},),
            executor=mock_executor.run,
        )
        assert resp_b.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "Alexandria" in resp_b.resolved_question
        assert "Cairo" not in resp_b.resolved_question

    def test_ambiguous_entity_returns_unresolved_clarification(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        conversation_router.route(
            "Show top customers.",
            conversation_id="conv_c5",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        # "And merchants?" is ambiguous
        resp = conversation_router.route(
            "And merchants?",
            conversation_id="conv_c5",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show top customers."},),
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.UNRESOLVED_CONTEXT
        assert resp.is_success is False
        assert "clarify" in resp.error_message.lower()


# ==============================================================================
# Category D — Independent Questions & Topic Switching
# ==============================================================================
class TestCategoryDIndependentQueries:
    """AC-04, AC-15: Complete standalone queries must NEVER be classified as follow-ups."""

    def test_complete_query_different_entity_is_independent(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        conversation_router.route(
            "Show customers with credit score above 700.",
            conversation_id="conv_d1",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        resp_b = conversation_router.route(
            "Show all branches.",
            conversation_id="conv_d1",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show customers with credit score above 700."},),
            executor=mock_executor.run,
        )
        assert resp_b.route == ConversationRoute.NEW_DATABASE_QUERY

    def test_complete_query_same_table_different_scope_is_independent(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        conversation_router.route(
            "Show customers in Cairo.",
            conversation_id="conv_d2",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        resp_b = conversation_router.route(
            "Show customers in Alexandria.",
            conversation_id="conv_d2",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show customers in Cairo."},),
            executor=mock_executor.run,
        )
        # Complete standalone query must be NEW_DATABASE_QUERY
        assert resp_b.route == ConversationRoute.NEW_DATABASE_QUERY

    def test_complete_query_with_conjunction_prefix_is_independent(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        conversation_router.route(
            "Show top customers.",
            conversation_id="conv_d3",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        # "And show all merchants" has standalone verb and full structure
        resp_b = conversation_router.route(
            "And show all merchants.",
            conversation_id="conv_d3",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show top customers."},),
            executor=mock_executor.run,
        )
        assert resp_b.route == ConversationRoute.NEW_DATABASE_QUERY


# ==============================================================================
# Category E — Context Contamination Verification
# ==============================================================================
class TestCategoryEContextContamination:
    """AC-05 through AC-09: No WHERE, JOIN, TOP, ORDER BY, GROUP BY, or DATE filter leaks."""

    def test_independent_query_does_not_receive_previous_turns_in_prompt_context(
        self, conversation_router: ConversationRouter, mock_executor: MockExecutor
    ):
        # Simulate previous turn
        raw_history = (
            {"role": "user", "content": "Show customers in Cairo with credit score > 700."},
            {"role": "assistant", "content": "SELECT * FROM Customers WHERE City = 'Cairo' AND CreditScore > 700"},
        )
        resp_b = conversation_router.route(
            "Show all customers.",
            conversation_id="conv_e1",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=raw_history,
            executor=mock_executor.run,
        )
        assert resp_b.route == ConversationRoute.NEW_DATABASE_QUERY
        # Check what was passed to executor
        last_req = mock_executor.invocations[-1]
        assert last_req.question == "Show all customers."
        # CRITICAL VERIFICATION: raw_history must NOT be passed to CopilotAskRequest for independent queries!
        assert len(last_req.conversation) == 0

    def test_system_rls_correction_preserved_in_independent_query(
        self, conversation_router: ConversationRouter, mock_executor: MockExecutor
    ):
        raw_history = (
            {"role": "user", "content": "Show customers in Cairo."},
            {"role": "assistant", "content": "SELECT ..."},
            {"role": "system", "content": "RLS_CORRECTION: Ensure BranchId filter is applied"},
        )
        resp_b = conversation_router.route(
            "Show all branches.",
            conversation_id="conv_e2",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=raw_history,
            executor=mock_executor.run,
        )
        last_req = mock_executor.invocations[-1]
        assert len(last_req.conversation) == 1
        assert last_req.conversation[0]["role"] == "system"


# ==============================================================================
# Category F — Security Scope Isolation & RLS Boundary Invariants
# ==============================================================================
class TestCategoryFSecurityRLS:
    """AC-11, AC-12: BranchId and TenantId security isolation."""

    def test_branch_id_used_as_effective_tenant_id(self, conversation_router: ConversationRouter, mock_executor: MockExecutor):
        # Backend passes branch_id without explicit tenant_id
        resp = conversation_router.route(
            "Show top 10 merchants.",
            conversation_id="conv_f1",
            branch_id="branch_10",
            user_id="user_1",
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.NEW_DATABASE_QUERY

        # Second request from same branch_id hits replay cache
        resp_replay = conversation_router.route(
            "Show top 10 merchants.",
            conversation_id="conv_f1",
            branch_id="branch_10",
            user_id="user_1",
            executor=mock_executor.run,
        )
        assert resp_replay.route == ConversationRoute.EXACT_REPLAY

        # Request from branch_20 misses replay cache
        resp_other = conversation_router.route(
            "Show top 10 merchants.",
            conversation_id="conv_f1",
            branch_id="branch_20",
            user_id="user_1",
            executor=mock_executor.run,
        )
        assert resp_other.route != ConversationRoute.EXACT_REPLAY


# ==============================================================================
# Category G — Multi-Turn & Context Reset
# ==============================================================================
class TestCategoryGMultiTurnAndReset:
    """AC-14, AC-16: Context reset commands and multi-turn accumulation."""

    def test_context_reset_clears_prior_state_and_executes_independently(
        self, conversation_router: ConversationRouter, mock_executor: MockExecutor
    ):
        # Turn 1
        conversation_router.route(
            "Show customers in Cairo.",
            conversation_id="conv_g1",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        # Turn 2: Explicit context reset
        resp = conversation_router.route(
            "New question: show all merchants.",
            conversation_id="conv_g1",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show customers in Cairo."},),
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.NEW_DATABASE_QUERY
        last_req = mock_executor.invocations[-1]
        assert "show all merchants" in last_req.question.lower()
        assert len(last_req.conversation) == 0

    def test_forget_previous_query_reset(
        self, conversation_router: ConversationRouter, mock_executor: MockExecutor
    ):
        conversation_router.route(
            "Show customers in Cairo.",
            conversation_id="conv_g2",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        resp = conversation_router.route(
            "Forget the previous query. Show all branches.",
            conversation_id="conv_g2",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show customers in Cairo."},),
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.NEW_DATABASE_QUERY
        last_req = mock_executor.invocations[-1]
        assert "show all branches" in last_req.question.lower()
        assert len(last_req.conversation) == 0

    def test_multi_turn_continuation_chain(
        self, conversation_router: ConversationRouter, mock_executor: MockExecutor
    ):
        # Turn 1: Base
        resp1 = conversation_router.route(
            "Show customers in Cairo.",
            conversation_id="conv_g3",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        assert resp1.route == ConversationRoute.NEW_DATABASE_QUERY

        # Turn 2: Filter addition
        resp2 = conversation_router.route(
            "Only those with credit score above 700.",
            conversation_id="conv_g3",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=({"role": "user", "content": "Show customers in Cairo."},),
            executor=mock_executor.run,
        )
        assert resp2.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "credit score" in resp2.resolved_question.lower()

        # Turn 3: Sort addition
        resp3 = conversation_router.route(
            "Sort them by balance.",
            conversation_id="conv_g3",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=(
                {"role": "user", "content": "Show customers in Cairo."},
                {"role": "user", "content": "Only those with credit score above 700."},
            ),
            executor=mock_executor.run,
        )
        assert resp3.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "balance" in resp3.resolved_question.lower()

        # Turn 4: Limit addition
        resp4 = conversation_router.route(
            "Only show the top 5.",
            conversation_id="conv_g3",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=(
                {"role": "user", "content": "Show customers in Cairo."},
                {"role": "user", "content": "Only those with credit score above 700."},
                {"role": "user", "content": "Sort them by balance."},
            ),
            executor=mock_executor.run,
        )
        assert resp4.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "5" in resp4.resolved_question

        # Turn 5: Topic switch to independent
        resp5 = conversation_router.route(
            "Show all branches.",
            conversation_id="conv_g3",
            tenant_id="tenant_1",
            user_id="user_1",
            raw_conversation=(
                {"role": "user", "content": "Show customers in Cairo."},
                {"role": "user", "content": "Only those with credit score above 700."},
                {"role": "user", "content": "Sort them by balance."},
                {"role": "user", "content": "Only show the top 5."},
            ),
            executor=mock_executor.run,
        )
        assert resp5.route == ConversationRoute.NEW_DATABASE_QUERY
        last_req = mock_executor.invocations[-1]
        assert last_req.question == "Show all branches."
        assert len(last_req.conversation) == 0  # No customer/Cairo/balance state in prompt!
