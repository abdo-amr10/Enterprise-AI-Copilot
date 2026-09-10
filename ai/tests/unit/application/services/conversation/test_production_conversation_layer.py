"""Comprehensive test suite for the production-grade AI Conversation Layer."""

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
    FollowupDetectionResult,
    FollowupType,
)
from src.application.services.conversation.normalization.normalizer import (
    RequestNormalizer,
)
from src.application.services.conversation.replay.fingerprint import (
    compute_fingerprint,
)
from src.application.services.conversation.replay.replay_cache import (
    InMemoryReplayRepository,
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
from src.application.services.conversation.router.scope_guard import ScopeGuard
from src.application.services.conversation.state.conversation_state import (
    ConversationState,
    ExecutionRecord,
    ResultMetadata,
    SemanticQueryState,
)
from src.application.services.conversation.state.state_manager import (
    ConversationStateManager,
)


# ==============================================================================
# 1. Request Normalization Tests
# ==============================================================================

def test_normalization_whitespace_and_casing():
    raw = "   Show   Top   5   Customers   in   Cairo?   "
    expected = "show top 5 customers in cairo"
    assert RequestNormalizer.normalize(raw) == expected


def test_normalization_punctuation_and_quotes():
    raw = "  \"Show total revenue for Q3?\"!  "
    normalized = RequestNormalizer.normalize(raw)
    assert normalized == "show total revenue for q3"


def test_normalization_semantic_distinctions_preserved():
    # Numbers must remain distinct
    assert RequestNormalizer.normalize("Top 5 customers") != RequestNormalizer.normalize("Top 10 customers")
    # Dates must remain distinct
    assert RequestNormalizer.normalize("January 2025") != RequestNormalizer.normalize("January 2026")
    # Dimensions must remain distinct
    assert RequestNormalizer.normalize("sales") != RequestNormalizer.normalize("sales by region")


# ==============================================================================
# 2. Exact Replay & Fingerprint Safety Tests
# ==============================================================================

def test_exact_replay_hit_same_context():
    replay_repo = InMemoryReplayRepository()
    replay_mgr = ExactReplayManager(replay_repo)

    q = "Show top 5 customers by revenue"
    replay_mgr.record_success(
        q,
        "SELECT TOP 5 * FROM customers ORDER BY revenue DESC;",
        tenant_id="tenant_alpha",
        user_id="user_123",
        semantic_revision_id="rev_1",
        schema_version="v1",
        conversation_id="conv_1",
    )

    result = replay_mgr.lookup(
        q,
        tenant_id="tenant_alpha",
        user_id="user_123",
        semantic_revision_id="rev_1",
        schema_version="v1",
        conversation_id="conv_1",
    )
    assert result.is_valid is True
    assert result.entry is not None
    assert result.entry.sql == "SELECT TOP 5 * FROM customers ORDER BY revenue DESC;"


def test_exact_replay_isolation_different_tenant():
    replay_mgr = ExactReplayManager(InMemoryReplayRepository())
    q = "Show sales by branch"
    replay_mgr.record_success(
        q,
        "SELECT * FROM sales;",
        tenant_id="tenant_alpha",
        user_id="user_123",
        semantic_revision_id="rev_1",
        schema_version="v1",
    )

    result = replay_mgr.lookup(
        q,
        tenant_id="tenant_beta",  # Different tenant!
        user_id="user_123",
        semantic_revision_id="rev_1",
        schema_version="v1",
    )
    assert result.is_valid is False
    assert result.reason_for_miss in ("CACHE_ENTRY_NOT_FOUND", "TENANT_SCOPE_MISMATCH")


def test_exact_replay_isolation_different_permission_scope():
    replay_mgr = ExactReplayManager(InMemoryReplayRepository())
    q = "Show manager salaries"
    replay_mgr.record_success(
        q,
        "SELECT * FROM salaries;",
        tenant_id="tenant_alpha",
        user_id="admin_user",
        semantic_revision_id="rev_1",
        schema_version="v1",
    )

    result = replay_mgr.lookup(
        q,
        tenant_id="tenant_alpha",
        user_id="regular_user",  # Different user/authorization scope!
        semantic_revision_id="rev_1",
        schema_version="v1",
    )
    assert result.is_valid is False
    assert result.reason_for_miss in ("CACHE_ENTRY_NOT_FOUND", "AUTHORIZATION_SCOPE_MISMATCH")


def test_exact_replay_isolation_different_semantic_revision():
    replay_mgr = ExactReplayManager(InMemoryReplayRepository())
    q = "Total revenue for 2024"
    replay_mgr.record_success(
        q,
        "SELECT SUM(revenue) FROM sales;",
        tenant_id="tenant_alpha",
        user_id="user_123",
        semantic_revision_id="rev_1",
        schema_version="v1",
    )

    result = replay_mgr.lookup(
        q,
        tenant_id="tenant_alpha",
        user_id="user_123",
        semantic_revision_id="rev_2",  # Different revision!
        schema_version="v1",
    )
    assert result.is_valid is False
    assert result.reason_for_miss in ("CACHE_ENTRY_NOT_FOUND", "SEMANTIC_REVISION_MISMATCH")


def test_exact_replay_negative_result_isolation():
    replay_mgr = ExactReplayManager(InMemoryReplayRepository())
    q1 = "Find employee Ahmed"
    replay_mgr.record_negative_result(
        q1,
        outcome_type="NO_ROWS_FOUND",
        text_summary="No rows found for employee Ahmed.",
        tenant_id="tenant_alpha",
        user_id="user_123",
        semantic_revision_id="rev_1",
        schema_version="v1",
    )

    # Replay for the exact same query works
    res1 = replay_mgr.lookup(
        q1,
        tenant_id="tenant_alpha",
        user_id="user_123",
        semantic_revision_id="rev_1",
        schema_version="v1",
    )
    assert res1.is_valid is True
    assert res1.entry.is_negative_result is True

    # But Query B ("What is Ahmed's department?") MUST NOT reuse the negative cache!
    q2 = "What is Ahmed's department?"
    res2 = replay_mgr.lookup(
        q2,
        tenant_id="tenant_alpha",
        user_id="user_123",
        semantic_revision_id="rev_1",
        schema_version="v1",
    )
    assert res2.is_valid is False


# ==============================================================================
# 3. Result-Aware Resolution Tests (No SQL, No LLM)
# ==============================================================================

def test_result_answer_ordinal_rank():
    resolver = ResultResolver()
    metadata = ResultMetadata(
        columns=("CustomerName", "Revenue", "Country"),
        row_count=10,
        sample_rows=(
            ("Alpha Corp", 100000, "Egypt"),
            ("Beta LLC", 80000, "UAE"),
            ("Gamma Inc", 60000, "Saudi Arabia"),
            ("Delta Co", 40000, "Egypt"),
        ),
    )

    outcome = resolver.resolve("Who is #3?", metadata)
    assert outcome.status == ResultResolutionStatus.ANSWERABLE
    assert "Gamma Inc" in outcome.answer
    assert outcome.referenced_row_index == 2


def test_result_answer_cell_attribute_lookup():
    resolver = ResultResolver()
    metadata = ResultMetadata(
        columns=("Name", "Salary", "Department"),
        row_count=2,
        sample_rows=(
            ("Sara", 15000, "Engineering"),
            ("Tamer", 12000, "Sales"),
        ),
    )

    outcome = resolver.resolve("What department is Sara in?", metadata)
    assert outcome.status == ResultResolutionStatus.ANSWERABLE
    assert outcome.answer == "Engineering"
    assert outcome.referenced_column == "Department"


def test_result_safety_missing_attribute_does_not_hallucinate():
    resolver = ResultResolver()
    # Notice: 'Department' is NOT in columns!
    metadata = ResultMetadata(
        columns=("Name", "Salary"),
        row_count=2,
        sample_rows=(
            ("Sara", 15000),
            ("Tamer", 12000),
        ),
    )

    # Asking for department when it's not in the result MUST return NOT_ANSWERABLE
    outcome = resolver.resolve("What department is Sara in?", metadata)
    assert outcome.status == ResultResolutionStatus.NOT_ANSWERABLE


def test_result_answer_extreme_max():
    resolver = ResultResolver()
    metadata = ResultMetadata(
        columns=("Region", "TotalSales"),
        row_count=3,
        sample_rows=(
            ("North", 1500),
            ("South", 900),
            ("East", 2400),
        ),
    )

    outcome = resolver.resolve("Which region is highest?", metadata)
    assert outcome.status == ResultResolutionStatus.ANSWERABLE
    assert "East" in outcome.answer
    assert "highest" in outcome.answer


def test_result_answer_row_count():
    resolver = ResultResolver()
    metadata = ResultMetadata(
        columns=("Id", "Name"),
        row_count=42,
        sample_rows=(),
    )

    outcome = resolver.resolve("How many rows?", metadata)
    assert outcome.status == ResultResolutionStatus.ANSWERABLE
    assert "42" in outcome.answer


# ==============================================================================
# 4. Follow-Up Detection & Continuation Tests
# ==============================================================================

def test_followup_detection_operations():
    detector = FollowupDetector()

    # Time change
    res1 = detector.detect("What about February?", has_history=True)
    assert res1.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED
    assert res1.operation_type == FollowupType.TIME_CHANGE
    assert res1.target_value == "february"

    # Limit change
    res2 = detector.detect("Make it top 5", has_history=True)
    assert res2.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED
    assert res2.operation_type == FollowupType.LIMIT_CHANGE
    assert res2.target_value == "5"

    # Group by change
    res3 = detector.detect("Group it by region", has_history=True)
    assert res3.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED
    assert res3.operation_type == FollowupType.GROUP_BY_CHANGE
    assert res3.target_value == "region"

    # Filter addition
    res4 = detector.detect("Only managers", has_history=True)
    assert res4.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED
    assert res4.operation_type == FollowupType.FILTER_CHANGE
    assert res4.target_value == "managers"

    # Correction
    res5 = detector.detect("No, I meant Cairo", has_history=True)
    assert res5.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED
    assert res5.operation_type == FollowupType.CORRECTION
    assert res5.target_value == "cairo"

    # Ambiguous anaphoric pronoun
    res6 = detector.detect("What about it?", has_history=True)
    assert res6.confidence_level == FollowupConfidence.UNRESOLVED

    # A concrete filter correction must update the prior intent, rather than
    # being treated as a semantically similar replay of the old query.
    res7 = detector.detect("Change it to 2025", has_history=True)
    assert res7.confidence_level == FollowupConfidence.FOLLOW_UP_CONFIRMED
    assert res7.operation_type == FollowupType.TIME_CHANGE
    assert res7.target_value == "2025"


def test_continuation_resolver_semantic_update_no_sql_mutation():
    resolver = ContinuationResolver()
    state = ConversationState(
        conversation_id="c1",
        active_query_state=SemanticQueryState(
            entities=("customers",),
            metrics=("revenue",),
            limit=10,
            raw_sql="SELECT TOP 10 name, revenue FROM customers ORDER BY revenue DESC;",
        ),
    )

    followup = FollowupDetectionResult(
        confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
        operation_type=FollowupType.LIMIT_CHANGE,
        target_value="5",
    )

    res = resolver.resolve(
        "Make it top 5",
        state,
        followup,
        prior_question="Show top 10 customers by revenue",
    )

    assert res.is_resolved is True
    assert "top 5" in res.resolved_question.lower()
    # Structured state is updated
    assert res.updated_semantic_state.limit == 5
    # Raw SQL string was NOT mutated via string.replace!
    assert res.updated_semantic_state.raw_sql == state.active_query_state.raw_sql


def test_time_correction_rewrites_the_prior_question_before_sql_generation():
    resolver = ContinuationResolver()
    state = ConversationState(conversation_id="date_correction")
    followup = FollowupDetectionResult(
        confidence_level=FollowupConfidence.FOLLOW_UP_CONFIRMED,
        operation_type=FollowupType.TIME_CHANGE,
        target_value="2025",
    )

    result = resolver.resolve(
        "Change it to 2025",
        state,
        followup,
        prior_question="Show all transactions made after January 1, 2026.",
    )

    assert result.is_resolved is True
    assert "2025" in result.resolved_question
    assert "2026" not in result.resolved_question
    assert result.updated_semantic_state.time_range == "2025"


def test_router_executes_date_correction_instead_of_replaying_prior_sql():
    router = ConversationRouter()
    executed_questions = []

    def executor(request):
        executed_questions.append(request.question)
        return TextToSQLRuntimeResponse.success("SELECT 1;")

    decision = router.route(
        "Change it to 2025",
        raw_conversation=(
            {
                "role": "turn",
                "user_question": "Show all transactions made after January 1, 2026.",
                "generated_sql": "SELECT * FROM transactions WHERE transaction_date >= '2026-01-01';",
                "execution_status": "Completed",
            },
        ),
        conversation_id="date_correction_router",
        tenant_id="tenant_1",
        user_id="user_1",
        executor=executor,
    )

    assert decision.route == ConversationRoute.FOLLOW_UP_QUERY
    assert executed_questions == ["Show all transactions made after January 1, 2025."]


def test_router_reuses_resolved_follow_up_sql_without_reinvoking_text_to_sql():
    router = ConversationRouter()
    executed_questions = []
    history = (
        {
            "role": "turn",
            "user_question": "Show all transactions made after January 1, 2026.",
            "generated_sql": "SELECT * FROM transactions WHERE transaction_date >= '2026-01-01';",
            "execution_status": "Completed",
        },
    )

    def executor(request):
        executed_questions.append(request.question)
        return TextToSQLRuntimeResponse.success("SELECT 1;")

    first = router.route(
        "Change it to 2025",
        raw_conversation=history,
        conversation_id="cached_date_correction",
        tenant_id="branch_1",
        user_id="user_1",
        executor=executor,
    )
    second = router.route(
        "Update it to 2025",
        raw_conversation=history,
        conversation_id="cached_date_correction",
        tenant_id="branch_1",
        user_id="user_1",
        executor=executor,
    )

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.cache_type == "RESOLVED_FOLLOW_UP_REPLAY"
    assert executed_questions == ["Show all transactions made after January 1, 2025."]


# ==============================================================================
# 5. Scope Guard / Early Safe Rejection Tests
# ==============================================================================

def test_scope_guard_rejections():
    # General knowledge
    assert ScopeGuard.evaluate("What is the capital of France?").is_in_scope is False
    assert ScopeGuard.evaluate("Who was the president of Egypt in 1970?").is_in_scope is False

    # Creative
    assert ScopeGuard.evaluate("Write a poem about database indexing").is_in_scope is False
    assert ScopeGuard.evaluate("Tell me a joke").is_in_scope is False

    # Chit-chat
    assert ScopeGuard.evaluate("What do you think about politics?").is_in_scope is False
    assert ScopeGuard.evaluate("How are you doing today?").is_in_scope is False

    # In-scope enterprise queries
    assert ScopeGuard.evaluate("Show total sales by region").is_in_scope is True
    assert ScopeGuard.evaluate("How many employees joined in 2025?").is_in_scope is True


# ==============================================================================
# 6. End-to-End Router Cascade Tests
# ==============================================================================

def test_router_cascade_exact_replay_short_circuits_text_to_sql():
    router = ConversationRouter()
    called_executor = []

    def mock_executor(req: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        called_executor.append(req.question)
        return TextToSQLRuntimeResponse.success("SELECT * FROM sales;")

    # 1. First execution with explicit security context
    decision1 = router.route(
        "Show sales by country",
        executor=mock_executor,
        conversation_id="conv_test",
        tenant_id="tenant_alpha",
        user_id="user_1",
    )
    assert decision1.route == ConversationRoute.NEW_DATABASE_QUERY
    assert len(called_executor) == 1

    # 2. Exact same execution with matching security context -> exact replay hit!
    decision2 = router.route(
        "Show sales by country",
        executor=mock_executor,
        conversation_id="conv_test",
        tenant_id="tenant_alpha",
        user_id="user_1",
    )
    assert decision2.route == ConversationRoute.EXACT_REPLAY
    assert decision2.cache_hit is True
    # Executor was NOT called a second time!
    assert len(called_executor) == 1


def test_router_cascade_exact_replay_bypassed_without_security_context():
    router = ConversationRouter()
    called_executor = []

    def mock_executor(req: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        called_executor.append(req.question)
        return TextToSQLRuntimeResponse.success("SELECT * FROM sales;")

    # First call without tenant_id or user_id
    decision1 = router.route("Show sales by country", executor=mock_executor, conversation_id="conv_unauth")
    assert decision1.route == ConversationRoute.NEW_DATABASE_QUERY
    assert len(called_executor) == 1

    # Second identical call without security context -> Replay is bypassed for security!
    decision2 = router.route("Show sales by country", executor=mock_executor, conversation_id="conv_unauth")
    assert decision2.route == ConversationRoute.NEW_DATABASE_QUERY
    assert decision2.cache_hit is False
    assert len(called_executor) == 2


def test_router_cascade_result_answering_bypasses_text_to_sql():
    router = ConversationRouter()
    conv_id = "conv_result"

    # Pre-populate state with query result
    state = router.state_manager.get_or_create_state(conv_id)
    state.last_result_metadata = ResultMetadata(
        columns=("Customer", "Revenue"),
        row_count=3,
        sample_rows=(
            ("Alpha Corp", 1000),
            ("Beta Corp", 2000),
            ("Gamma Corp", 3000),
        ),
    )

    executor_called = []
    def mock_executor(req):
        executor_called.append(req.question)
        return TextToSQLRuntimeResponse.success("SELECT 1;")

    decision = router.route("Who is #2?", conversation_id=conv_id, executor=mock_executor)
    assert decision.route == ConversationRoute.RESULT_ANSWER
    assert "Beta Corp" in decision.text_summary
    assert decision.generated_sql is None
    # Text-to-SQL executor was NOT invoked
    assert len(executor_called) == 0


def test_router_cascade_out_of_scope_safely_rejected_before_text_to_sql():
    router = ConversationRouter()
    executor_called = []
    def mock_executor(req):
        executor_called.append(req.question)
        return TextToSQLRuntimeResponse.success("SELECT 1;")

    decision = router.route("What is the capital of France?", executor=mock_executor)
    assert decision.route == ConversationRoute.UNSUPPORTED
    assert decision.is_success is False
    assert "I can only help with questions about your data" in decision.error_message
    # Text-to-SQL executor was NEVER called for out-of-scope question!
    assert len(executor_called) == 0


def test_state_manager_update_rules():
    mgr = ConversationStateManager()
    conv_id = "test_rules"

    # 1. Successful execution updates state and increments version
    state = mgr.record_successful_execution(
        conv_id,
        sql="SELECT * FROM orders;",
        query_state=SemanticQueryState(entities=("orders",)),
    )
    assert state.state_version == 2
    assert state.active_query_state.entities == ("orders",)

    # 2. Result answer does NOT overwrite active DB query state
    state2 = mgr.record_result_answer(conv_id, question="Who is #1?", answer="Order 123")
    assert state2.active_query_state.entities == ("orders",)

    # 3. Unsupported request does NOT corrupt active DB query state
    state3 = mgr.record_unsupported_request(conv_id)
    assert state3.active_query_state.entities == ("orders",)

    # 4. Failed execution does NOT promote failed query to active successful state
    state4 = mgr.record_execution_failure(
        conv_id,
        sql="DROP TABLE orders;",
        error_code="FORBIDDEN",
        error_message="Write not allowed",
    )
    assert state4.last_successful_execution.sql == "SELECT * FROM orders;"


# ==============================================================================
# 7. Multi-Tenant Concurrency & Security Isolation Tests
# ==============================================================================

def test_concurrency_multi_tenant_isolation():
    """User A (Tenant A) and User B (Tenant B) asking the identical query simultaneously.

    Asserts zero cache collision across tenant boundaries.
    """
    router = ConversationRouter()
    tenant_a_calls = []
    tenant_b_calls = []

    def mock_executor_a(req: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        tenant_a_calls.append(req.question)
        return TextToSQLRuntimeResponse.success("SELECT * FROM tenant_a_data;")

    def mock_executor_b(req: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        tenant_b_calls.append(req.question)
        return TextToSQLRuntimeResponse.success("SELECT * FROM tenant_b_data;")

    # 1. Tenant A executes query
    q = "Show monthly revenue"
    dec_a1 = router.route(
        q,
        tenant_id="tenant_a",
        user_id="user_alice",
        conversation_id="conv_a",
        executor=mock_executor_a,
    )
    assert dec_a1.route == ConversationRoute.NEW_DATABASE_QUERY
    assert dec_a1.generated_sql == "SELECT * FROM tenant_a_data;"
    assert len(tenant_a_calls) == 1

    # 2. Tenant B executes identical query -> must NOT hit Tenant A's cache!
    dec_b1 = router.route(
        q,
        tenant_id="tenant_b",
        user_id="user_bob",
        conversation_id="conv_b",
        executor=mock_executor_b,
    )
    assert dec_b1.route == ConversationRoute.NEW_DATABASE_QUERY
    assert dec_b1.generated_sql == "SELECT * FROM tenant_b_data;"
    assert len(tenant_b_calls) == 1
    assert dec_b1.cache_hit is False

    # 3. Tenant A executes again -> hits Tenant A's exact replay cache cleanly
    dec_a2 = router.route(
        q,
        tenant_id="tenant_a",
        user_id="user_alice",
        conversation_id="conv_a",
        executor=mock_executor_a,
    )
    assert dec_a2.route == ConversationRoute.EXACT_REPLAY
    assert dec_a2.generated_sql == "SELECT * FROM tenant_a_data;"
    assert len(tenant_a_calls) == 1  # Executor not called again


def test_cold_start_reconstruction_from_backend_metadata():
    """AI Runtime restarted (clean memory).

    Backend sends conversation history with structured execution metadata.
    Asserts state is reconstructed and direct result answering works immediately.
    """
    fresh_router = ConversationRouter()  # Empty in-memory state
    conv_id = "restarted_session_42"

    raw_history = (
        {"role": "user", "content": "Show top 3 products by metric"},
        {
            "role": "assistant",
            "content": "Generated SQL: SELECT product, metric FROM catalog ORDER BY metric DESC LIMIT 3;",
            "execution_result": {
                "columns": ["Product", "Metric"],
                "rowCount": 3,
                "rows": [
                    ["AlphaWidget", 950],
                    ["BetaWidget", 820],
                    ["GammaWidget", 710],
                ],
            },
            "execution_result_summary": "Top product was AlphaWidget with 950 metric.",
        },
    )

    # User asks direct result question on cold AI instance
    decision = fresh_router.route(
        "Who is #1?",
        raw_conversation=raw_history,
        conversation_id=conv_id,
        tenant_id="tenant_core",
        user_id="user_analyst",
    )

    assert decision.route == ConversationRoute.RESULT_ANSWER
    assert decision.presentation_type == "DirectAnswer"
    assert "AlphaWidget" in decision.text_summary
    assert decision.generated_sql is None


def test_semantic_revision_change_bypasses_replay():
    """Same query, same tenant/user, but semantic layer revision changed.

    Asserts cached SQL from older revision is NOT reused.
    """
    router = ConversationRouter()
    calls = []

    def mock_executor(req: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        calls.append(req.question)
        return TextToSQLRuntimeResponse.success("SELECT * FROM v1;")

    q = "Show all transactions"
    # Execute under Revision 1
    r1 = router.route(
        q,
        tenant_id="tenant_x",
        user_id="user_1",
        semantic_revision_id="rev_1",
        executor=mock_executor,
    )
    assert r1.route == ConversationRoute.NEW_DATABASE_QUERY
    assert len(calls) == 1

    # Execute under Revision 2 -> Replay must be invalidated/bypassed!
    r2 = router.route(
        q,
        tenant_id="tenant_x",
        user_id="user_1",
        semantic_revision_id="rev_2",
        executor=mock_executor,
    )
    assert r2.route == ConversationRoute.NEW_DATABASE_QUERY
    assert len(calls) == 2


def test_permission_change_bypasses_replay():
    """Same query, same tenant, but different user/permission scope.

    Asserts cached SQL is never leaked to a different user.
    """
    router = ConversationRouter()
    calls = []

    def mock_executor(req: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        calls.append(req.question)
        return TextToSQLRuntimeResponse.success("SELECT * FROM confidential;")

    q = "Show confidential accounts"
    # Admin executes
    r1 = router.route(
        q,
        tenant_id="tenant_x",
        user_id="admin_user",
        executor=mock_executor,
    )
    assert r1.route == ConversationRoute.NEW_DATABASE_QUERY
    assert len(calls) == 1

    # Regular user executes -> No replay
    r2 = router.route(
        q,
        tenant_id="tenant_x",
        user_id="standard_user",
        executor=mock_executor,
    )
    assert r2.route == ConversationRoute.NEW_DATABASE_QUERY
    assert len(calls) == 2


def test_direct_answer_preserves_active_semantic_query_state():
    """User asks follow-up on previous result -> answered directly.

    Asserts active SemanticQueryState is NOT overwritten or corrupted.
    """
    router = ConversationRouter()
    conv_id = "state_preservation_conv"

    # Step 1: Initial query
    def mock_executor(req):
        return TextToSQLRuntimeResponse.success("SELECT * FROM items;")

    router.route(
        "Show all items in stock",
        conversation_id=conv_id,
        tenant_id="t1",
        user_id="u1",
        executor=mock_executor,
    )
    st1 = router.state_manager.get_or_create_state(conv_id)
    assert st1.last_successful_execution.sql == "SELECT * FROM items;"
    original_query_state = st1.active_query_state

    # Add result metadata
    st1.last_result_metadata = ResultMetadata(
        columns=("Item", "Stock"),
        row_count=2,
        sample_rows=(("ItemA", 10), ("ItemB", 20)),
        tenant_id="t1",
        user_id="u1",
    )

    # Step 2: Result-only query
    dec_result = router.route(
        "Who is #1?",
        conversation_id=conv_id,
        tenant_id="t1",
        user_id="u1",
    )
    assert dec_result.route == ConversationRoute.RESULT_ANSWER
    assert dec_result.presentation_type == "DirectAnswer"
    assert "ItemA" in dec_result.text_summary

    # Step 3: Verify active query state was NOT overwritten by the result answer
    st2 = router.state_manager.get_or_create_state(conv_id)
    assert st2.active_query_state == original_query_state
    assert st2.last_successful_execution.sql == "SELECT * FROM items;"


def test_database_and_schema_agnosticism_with_abstract_metadata():
    """Verify complete database, schema, and domain agnosticism.

    Operates entirely over synthetic abstract tokens (metric_alpha, category_beta, val_gamma)
    with zero coupling to real business domains (employees, customers, salary, branches).
    """
    resolver = ResultResolver()
    metadata = ResultMetadata(
        columns=("category_beta", "metric_alpha", "val_gamma"),
        row_count=3,
        sample_rows=(
            ("delta_1", 150.5, "active"),
            ("delta_2", 320.0, "pending"),
            ("delta_3", 85.2, "archived"),
        ),
        tenant_id="tenant_abstract",
        user_id="user_abstract",
    )

    # 1. Ordinal rank lookup on abstract columns
    res_rank = resolver.resolve(
        "Who is #2?",
        metadata,
        current_tenant_id="tenant_abstract",
        current_user_id="user_abstract",
    )
    assert res_rank.status == ResultResolutionStatus.ANSWERABLE
    assert "delta_2" in res_rank.answer

    # 2. Extreme query on abstract numerical column
    res_max = resolver.resolve(
        "Which category_beta has the highest metric_alpha?",
        metadata,
        current_tenant_id="tenant_abstract",
        current_user_id="user_abstract",
    )
    assert res_max.status == ResultResolutionStatus.ANSWERABLE
    assert "delta_2" in res_max.answer
    assert "320.0" in res_max.answer

    # 3. Attribute lookup on abstract column
    res_attr = resolver.resolve(
        "What is the val_gamma of delta_3?",
        metadata,
        current_tenant_id="tenant_abstract",
        current_user_id="user_abstract",
    )
    assert res_attr.status == ResultResolutionStatus.ANSWERABLE
    assert res_attr.answer == "archived"

    # 4. Missing attribute returns NOT_ANSWERABLE (zero hallucination)
    res_missing = resolver.resolve(
        "What is the unknown_dimension_omega of delta_1?",
        metadata,
        current_tenant_id="tenant_abstract",
        current_user_id="user_abstract",
    )
    assert res_missing.status == ResultResolutionStatus.NOT_ANSWERABLE

    # 5. Security scope mismatch rejects resolution
    res_unauth = resolver.resolve(
        "Who is #1?",
        metadata,
        current_tenant_id="different_tenant",
        current_user_id="user_abstract",
    )
    assert res_unauth.status == ResultResolutionStatus.NOT_ANSWERABLE
    assert "Security tenant scope mismatch" in res_unauth.reason

