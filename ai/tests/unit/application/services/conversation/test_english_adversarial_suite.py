"""Comprehensive English Real-World & Adversarial Test Suite for the Conversation Layer.

Verifies:
1. Exact Replay and Cache Scoping
2. Result-Aware Answering (Zero-Hallucination, Multi-Column Ambiguity Prevention)
3. Follow-up Query Continuation (Replacements, Additions, Anaphora)
4. Context Contamination Prevention (Prompt-level and AST-level isolation)
5. Out-of-Scope Early Rejections (Creative, Trivia, Chit-Chat, Weather)
6. Security Boundary Enforcement (Tenant, User, Branch RLS)
7. Multi-Turn Dialog Chains and Context Resets
"""

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
from src.application.services.conversation.replay.replay_manager import (
    ExactReplayManager,
)
from src.application.services.conversation.result_resolution.models import (
    ResultResolutionOutcome,
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
from src.application.services.conversation.router.scope_guard import (
    ScopeGuard,
)
from src.application.services.conversation.state.conversation_state import (
    ConversationState,
    ResultMetadata,
    SemanticQueryState,
)


class MockEnglishExecutor:
    """Mock Text-to-SQL pipeline executor."""

    def __init__(self, default_sql: str = "SELECT * FROM english_table;") -> None:
        self.invocations: list[CopilotAskRequest] = []
        self.default_sql = default_sql

    def run(self, request: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        self.invocations.append(request)
        return TextToSQLRuntimeResponse.success(self.default_sql)


@pytest.fixture
def router() -> ConversationRouter:
    return ConversationRouter()


@pytest.fixture
def executor() -> MockEnglishExecutor:
    return MockEnglishExecutor()


# ==============================================================================
# SECTION 1: Exact Replay and Cache Scoping (English)
# ==============================================================================
class TestEnglishExactReplay:
    def test_exact_replay_hit(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """Identical English query hits replay cache, skipping Text-to-SQL."""
        r1 = router.route("Show customers with balance > 5000", conversation_id="c_rep1", tenant_id="t1", user_id="u1", executor=executor.run)
        assert r1.route == ConversationRoute.NEW_DATABASE_QUERY
        assert len(executor.invocations) == 1

        r2 = router.route("Show customers with balance > 5000", conversation_id="c_rep1", tenant_id="t1", user_id="u1", executor=executor.run)
        assert r2.route == ConversationRoute.EXACT_REPLAY
        assert r2.cache_hit is True
        assert len(executor.invocations) == 1  # No 2nd invocation

    def test_exact_replay_whitespace_and_case_insensitive(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """Normalized whitespace and casing hits cache."""
        router.route("Show all active employees", conversation_id="c_rep2", tenant_id="t1", user_id="u1", executor=executor.run)
        r2 = router.route("  SHOW   ALL   active   EMPLOYEES  ", conversation_id="c_rep2", tenant_id="t1", user_id="u1", executor=executor.run)
        assert r2.route == ConversationRoute.EXACT_REPLAY

    def test_replay_rejected_on_different_tenant(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """Cross-tenant cache access is strictly prevented."""
        router.route("Show all transactions", conversation_id="c_rep3", tenant_id="tenant_A", user_id="u1", executor=executor.run)
        r2 = router.route("Show all transactions", conversation_id="c_rep3", tenant_id="tenant_B", user_id="u1", executor=executor.run)
        assert r2.route != ConversationRoute.EXACT_REPLAY
        assert len(executor.invocations) == 2

    def test_replay_rejected_on_different_user(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """Cross-user cache access is strictly prevented."""
        router.route("Show salary reports", conversation_id="c_rep4", tenant_id="t1", user_id="manager_1", executor=executor.run)
        r2 = router.route("Show salary reports", conversation_id="c_rep4", tenant_id="t1", user_id="manager_2", executor=executor.run)
        assert r2.route != ConversationRoute.EXACT_REPLAY

    def test_replay_rejected_on_predicate_change(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """Modifying predicate from > 5000 to > 6000 triggers new execution."""
        router.route("Show customers with balance > 5000", conversation_id="c_rep5", tenant_id="t1", user_id="u1", executor=executor.run)
        r2 = router.route("Show customers with balance > 6000", conversation_id="c_rep5", tenant_id="t1", user_id="u1", executor=executor.run)
        assert r2.route != ConversationRoute.EXACT_REPLAY
        assert len(executor.invocations) == 2


# ==============================================================================
# SECTION 2: Result-Aware Answering & Zero-Hallucination (English)
# ==============================================================================
class TestEnglishResultResolution:
    def test_count_answer_from_result_metadata(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """'How many rows?' answers directly without LLM/SQL."""
        meta = ResultMetadata(columns=("id", "name"), row_count=7, sample_rows=())
        resp = router.route("How many rows?", conversation_id="c_res1", last_result_metadata=meta, executor=executor.run)
        assert resp.route == ConversationRoute.RESULT_ANSWER
        assert "7 rows" in resp.text_summary
        assert len(executor.invocations) == 0

    def test_ordinal_answer_from_result_metadata(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """'Who is #1?' returns first row directly."""
        meta = ResultMetadata(
            columns=("CustomerName", "Revenue"),
            row_count=2,
            sample_rows=(("Acme Corp", 50000), ("Beta LLC", 30000)),
        )
        resp = router.route("Who is #1?", conversation_id="c_res2", last_result_metadata=meta, executor=executor.run)
        assert resp.route == ConversationRoute.RESULT_ANSWER
        assert "Acme Corp" in resp.text_summary
        assert len(executor.invocations) == 0

    def test_multi_column_ambiguity_fails_safely_without_guessing(self):
        """CRITICAL AUDIT RISK #2: When multiple numeric columns exist and metric is unspecified, DO NOT GUESS!"""
        resolver = ResultResolver()
        meta = ResultMetadata(
            columns=("name", "credit_score", "annual_salary", "loan_amount"),
            row_count=2,
            sample_rows=(("Alice", 780, 120000, 450000), ("Bob", 650, 90000, 300000)),
        )
        outcome = resolver.resolve("Who is the highest?", meta)
        assert outcome.status == ResultResolutionStatus.NOT_ANSWERABLE
        assert "Ambiguous metric" in (outcome.reason or "")

    def test_explicit_metric_resolves_accurately(self):
        """Specifying 'highest salary' picks annual_salary column accurately."""
        resolver = ResultResolver()
        meta = ResultMetadata(
            columns=("name", "credit_score", "annual_salary"),
            row_count=2,
            sample_rows=(("Alice", 780, 120000), ("Bob", 650, 150000)),
        )
        outcome = resolver.resolve("Who has the highest salary?", meta)
        assert outcome.status == ResultResolutionStatus.ANSWERABLE
        assert "Bob" in outcome.answer
        assert "150000" in outcome.answer

    def test_cell_attribute_lookup(self):
        """Attribute lookup: 'What is Alice's salary?'"""
        resolver = ResultResolver()
        meta = ResultMetadata(
            columns=("name", "department", "salary"),
            row_count=2,
            sample_rows=(("Alice", "Engineering", 120000), ("Bob", "Marketing", 95000)),
        )
        outcome = resolver.resolve("What is Alice's salary?", meta)
        assert outcome.status == ResultResolutionStatus.ANSWERABLE
        assert outcome.answer == "120000"

    def test_missing_attribute_does_not_hallucinate(self):
        """Asking for missing attribute 'phone' returns NOT_ANSWERABLE."""
        resolver = ResultResolver()
        meta = ResultMetadata(
            columns=("name", "department", "salary"),
            row_count=2,
            sample_rows=(("Alice", "Engineering", 120000), ("Bob", "Marketing", 95000)),
        )
        outcome = resolver.resolve("What is Alice's phone number?", meta)
        assert outcome.status == ResultResolutionStatus.NOT_ANSWERABLE


# ==============================================================================
# SECTION 3: Follow-Up Query Continuation (English)
# ==============================================================================
class TestEnglishFollowUpContinuation:
    def test_scope_substitution_city(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """'What about Alexandria?' substitutes Cairo."""
        router.route("Show customers in Cairo", conversation_id="c_fol1", executor=executor.run)
        resp = router.route("What about Alexandria?", conversation_id="c_fol1", executor=executor.run)
        assert resp.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "Alexandria" in (resp.resolved_question or "")

    def test_scope_substitution_products_domain_agnostic(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """Domain-agnostic product slot substitution: 'for laptops' -> 'for smartphones'."""
        router.route("List total revenue for laptops", conversation_id="c_prod", executor=executor.run)
        resp = router.route("What about smartphones?", conversation_id="c_prod", executor=executor.run)
        assert resp.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "smartphones" in (resp.resolved_question or "").lower()
        assert "laptops" not in (resp.resolved_question or "").lower()

    def test_scope_substitution_departments_domain_agnostic(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """Domain-agnostic department slot substitution: 'in Marketing' -> 'in Engineering'."""
        router.route("Show active employees in Marketing", conversation_id="c_dept", executor=executor.run)
        resp = router.route("What about Engineering?", conversation_id="c_dept", executor=executor.run)
        assert resp.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "Engineering" in (resp.resolved_question or "")
        assert "Marketing" not in (resp.resolved_question or "")

    def test_filter_replacement_with_actually_make_that(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """'Actually, make that 2026' modifies year filter."""
        router.route("Show total sales for 2025", conversation_id="c_fol2", executor=executor.run)
        resp = router.route("Actually, make that 2026", conversation_id="c_fol2", executor=executor.run)
        assert resp.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "2026" in (resp.resolved_question or "")
        assert "2025" not in (resp.resolved_question or "")

    def test_filter_replacement_numeric_condition(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """'Actually, below 600' modifies score condition."""
        router.route("Show customers with credit score above 700", conversation_id="c_fol3", executor=executor.run)
        resp = router.route("Actually, below 600", conversation_id="c_fol3", executor=executor.run)
        assert resp.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "below 600" in (resp.resolved_question or "").lower()

    def test_limit_change_followup(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """'Top 5 only' changes limit."""
        router.route("Show all customers in Cairo", conversation_id="c_fol4", executor=executor.run)
        resp = router.route("Top 5 only", conversation_id="c_fol4", executor=executor.run)
        assert resp.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "5" in (resp.resolved_question or "")

    def test_sorting_followup(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """'Sort them by balance descending' adds order_by."""
        router.route("Show all customers in Cairo", conversation_id="c_fol5", executor=executor.run)
        resp = router.route("Sort them by balance descending", conversation_id="c_fol5", executor=executor.run)
        assert resp.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "balance" in (resp.resolved_question or "").lower()

    def test_group_by_followup(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """'Group by department' adds group_by."""
        router.route("Show employee count", conversation_id="c_fol6", executor=executor.run)
        resp = router.route("Group by department", conversation_id="c_fol6", executor=executor.run)
        assert resp.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "department" in (resp.resolved_question or "").lower()

    def test_ambiguous_entity_returns_unresolved_clarification(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """'What about that?' returns UNRESOLVED_CONTEXT prompting user clarification."""
        router.route("Show customers in Cairo", conversation_id="c_fol7", executor=executor.run)
        resp = router.route("What about that?", conversation_id="c_fol7", executor=executor.run)
        assert resp.route == ConversationRoute.UNRESOLVED_CONTEXT


# ==============================================================================
# SECTION 4: Zero Context Contamination (English)
# ==============================================================================
class TestEnglishContextContamination:
    def test_independent_query_prompt_is_isolated(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """Independent query receives clean, isolated prompt context with zero prior user turns."""
        history = [
            {"role": "user", "content": "Show top 10 customers in Cairo with balance > 50000"},
            {"role": "assistant", "content": "Here are the top 10 customers..."},
        ]
        # Previous turn
        router.route("Show top 10 customers in Cairo with balance > 50000", conversation_id="c_iso1", raw_conversation=tuple(history[:1]), executor=executor.run)

        # Independent turn
        resp = router.route("Show all product categories", conversation_id="c_iso1", raw_conversation=tuple(history), executor=executor.run)
        assert resp.route == ConversationRoute.NEW_DATABASE_QUERY
        assert len(executor.invocations) == 2

        # Verify executor payload for turn 2 has NO prior conversation history
        second_request = executor.invocations[1]
        assert second_request.conversation == ()
        assert second_request.question == "Show all product categories"

    def test_no_predicate_or_limit_leakage_in_independent_turn(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """Prior limit 'top 3' and predicate 'score > 750' do not contaminate new independent query."""
        router.route("Show top 3 customers with score > 750", conversation_id="c_iso2", executor=executor.run)
        resp = router.route("Show all branches", conversation_id="c_iso2", executor=executor.run)
        assert resp.route == ConversationRoute.NEW_DATABASE_QUERY

        inv2 = executor.invocations[1]
        assert "score" not in inv2.question.lower()
        assert "750" not in inv2.question
        assert "top 3" not in inv2.question.lower()

    def test_system_rls_corrections_retained_while_user_turns_stripped(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """System corrections (like RLS enforcement) stay in prompt context, while user turns are stripped."""
        history = [
            {"role": "system", "content": "RLS_CORRECTION: enforce @UserBranchId"},
            {"role": "user", "content": "Show sales in region North"},
            {"role": "assistant", "content": "North region sales shown"},
        ]
        resp = router.route("Show all warehouse inventory", conversation_id="c_iso3", raw_conversation=tuple(history), executor=executor.run)
        assert resp.route == ConversationRoute.NEW_DATABASE_QUERY

        inv = executor.invocations[0]
        assert len(inv.conversation) == 1
        assert inv.conversation[0]["role"] == "system"
        assert "RLS_CORRECTION" in inv.conversation[0]["content"]

    def test_context_reset_via_new_question_prefix(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """'New question: Show all suppliers' wipes conversation context."""
        router.route("Show customers in Cairo", conversation_id="c_iso4", executor=executor.run)
        resp = router.route("New question: Show all suppliers", conversation_id="c_iso4", executor=executor.run)
        assert resp.route == ConversationRoute.NEW_DATABASE_QUERY
        assert resp.resolved_question == "Show all suppliers" or resp.generated_sql is not None


# ==============================================================================
# SECTION 5: Early Scope Guard Rejection (English)
# ==============================================================================
class TestEnglishScopeGuard:
    def test_reject_creative_writing_poem(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """Creative poem request rejected before Text-to-SQL."""
        resp = router.route("Write a poem about databases", conversation_id="c_sg1", executor=executor.run)
        assert resp.route == ConversationRoute.UNSUPPORTED
        assert len(executor.invocations) == 0

    def test_reject_creative_joke(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """Joke request rejected."""
        resp = router.route("Tell me a joke", conversation_id="c_sg2", executor=executor.run)
        assert resp.route == ConversationRoute.UNSUPPORTED
        assert len(executor.invocations) == 0

    def test_reject_trivia_capital(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """General knowledge trivia rejected."""
        resp = router.route("What is the capital of France?", conversation_id="c_sg3", executor=executor.run)
        assert resp.route == ConversationRoute.UNSUPPORTED
        assert len(executor.invocations) == 0

    def test_reject_weather(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """External weather question rejected."""
        resp = router.route("What is the weather in London?", conversation_id="c_sg4", executor=executor.run)
        assert resp.route == ConversationRoute.UNSUPPORTED
        assert len(executor.invocations) == 0

    def test_reject_chitchat_sentience(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """Chit-chat rejected."""
        resp = router.route("Are you sentient or alive?", conversation_id="c_sg5", executor=executor.run)
        assert resp.route == ConversationRoute.UNSUPPORTED
        assert len(executor.invocations) == 0


# ==============================================================================
# SECTION 6: Multi-Turn Dialog Chains (English)
# ==============================================================================
class TestEnglishMultiTurnDialogs:
    def test_complete_five_turn_conversation_flow(self, router: ConversationRouter, executor: MockEnglishExecutor):
        """5-Turn English conversation demonstrating the full lifecycle:
        Turn 1: Show customers in London (New Query)
        Turn 2: Top 10 only (Follow-up Limit)
        Turn 3: Who is #1? (Direct Result Answer without model)
        Turn 4: What about Paris? (Follow-up Location Change)
        Turn 5: New question: Show all suppliers (Clean New Query)
        """
        conv = "c_5turn_en"

        # Turn 1: Initial query
        t1 = router.route("Show customers in London", conversation_id=conv, executor=executor.run)
        assert t1.route == ConversationRoute.NEW_DATABASE_QUERY

        # Turn 2: Follow-up limit
        t2 = router.route("Top 10 only", conversation_id=conv, executor=executor.run)
        assert t2.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "10" in (t2.resolved_question or "")

        # Turn 3: Result answering
        meta = ResultMetadata(
            columns=("Customer", "Balance"),
            row_count=2,
            sample_rows=(("Acme Global", 85000), ("Beta Services", 42000)),
        )
        t3 = router.route("Who is #1?", conversation_id=conv, last_result_metadata=meta, executor=executor.run)
        assert t3.route == ConversationRoute.RESULT_ANSWER
        assert "Acme Global" in t3.text_summary

        # Turn 4: Filter change
        t4 = router.route("What about Paris?", conversation_id=conv, executor=executor.run)
        assert t4.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "Paris" in (t4.resolved_question or "")

        # Turn 5: Context reset
        t5 = router.route("New question: Show all suppliers", conversation_id=conv, executor=executor.run)
        assert t5.route == ConversationRoute.NEW_DATABASE_QUERY
