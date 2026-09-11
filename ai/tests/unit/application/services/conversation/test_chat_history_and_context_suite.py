"""Comprehensive test suite for multi-turn Chat History, Scope Retention, and Context Resolution.

Validates the full HIS-001 through HIS-010 synthetic banking scenario and verifies:
1. Referential signals are detected deterministically without domain hardcoding.
2. Active entity scope is preserved across failed/rejected schema validation turns (Turn 3 and 4).
3. ResultResolver never hijacks database query instructions into fake metadata answers.
4. ContinuationResolver dynamically extracts and substitutes entity scope domain-agnostically.
5. Separation of concerns: Conversation layer establishes scope, Text-to-SQL / Schema Validator owns rejecting nonexistent columns.
"""

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
    ConversationState,
    ExecutionRecord,
    ResultMetadata,
    SemanticQueryState,
)


def test_his_001_to_010_sequential_synthetic_banking_suite():
    """Validates the full 10-turn multi-turn conversation sequence (HIS-001 through HIS-010)."""
    router = ConversationRouter()
    conv_id = "conv_his_suite_10_turns"
    tenant_id = "tenant_banking"
    user_id = "analyst_1"

    executed_requests: list[CopilotAskRequest] = []
    conversation_history: list[dict] = []

    def mock_backend_executor(req: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        executed_requests.append(req)
        q_lower = req.question.lower()

        # Turn 3 rejection: phone_number does not exist in customers
        if "phone" in q_lower or "phone_number" in q_lower:
            return TextToSQLRuntimeResponse.failure(
                "INVALID_SCHEMA_COLUMN",
                "Column 'customers.phone_number' not found in schema.",
                failure_reason="Column 'customers.phone_number' does not exist.",
            )

        # Turn 4 rejection: branch_id does not exist in customers
        if "customers.branch_id" in q_lower or "branch_id" in q_lower and "using customers.branch_id" in q_lower:
            return TextToSQLRuntimeResponse.failure(
                "INVALID_SCHEMA_COLUMN",
                "Column 'customers.branch_id' not found in schema.",
                failure_reason="Column 'customers.branch_id' does not exist.",
            )

        # Turn 7 rejection: status does not exist in transactions
        if "transaction status" in q_lower or "transactions.status" in q_lower:
            return TextToSQLRuntimeResponse.failure(
                "INVALID_SCHEMA_COLUMN",
                "Column 'transactions.status' not found in schema.",
                failure_reason="Column 'transactions.status' does not exist.",
            )

        # Turn 9 rejection: preferred_branch_id does not exist
        if "preferred_branch_id" in q_lower:
            return TextToSQLRuntimeResponse.failure(
                "INVALID_SCHEMA_COLUMN",
                "Column 'preferred_branch_id' not found in schema.",
                failure_reason="Column 'preferred_branch_id' does not exist.",
            )

        # Turn 1: Show all customers
        if "show all customers" in q_lower:
            return TextToSQLRuntimeResponse.success(
                "SELECT customer_id, first_name, last_name, credit_score FROM customers;",
            )

        # Turn 2: Top 5 customers by credit score
        if "credit score" in q_lower and "5" in q_lower and "balance" not in q_lower and "transaction" not in q_lower:
            return TextToSQLRuntimeResponse.success(
                "SELECT customer_id, first_name, last_name, credit_score FROM customers ORDER BY credit_score DESC LIMIT 5;",
            )

        # Turn 5: Account balances for top 5 customers by credit score
        if "account balance" in q_lower or "balance" in q_lower and "transaction" not in q_lower:
            return TextToSQLRuntimeResponse.success(
                "SELECT c.customer_id, c.first_name, a.balance FROM customers c JOIN accounts a ON c.customer_id = a.customer_id ORDER BY c.credit_score DESC LIMIT 5;",
            )

        # Turn 6: Total transaction amount for top 5 customers by credit score
        if "total transaction amount" in q_lower and "greater than" not in q_lower and "finally" not in q_lower:
            return TextToSQLRuntimeResponse.success(
                "SELECT c.customer_id, c.first_name, SUM(t.amount) AS total_amount FROM customers c JOIN accounts a ON c.customer_id = a.customer_id JOIN transactions t ON a.account_id = t.account_id GROUP BY c.customer_id, c.first_name ORDER BY c.credit_score DESC LIMIT 5;",
            )

        # Turn 8: Greater than 10,000 USD
        if "10,000" in q_lower or "10000" in q_lower:
            return TextToSQLRuntimeResponse.success(
                "SELECT c.customer_id, c.first_name, SUM(t.amount) AS total_amount FROM customers c JOIN accounts a ON c.customer_id = a.customer_id JOIN transactions t ON a.account_id = t.account_id GROUP BY c.customer_id, c.first_name HAVING SUM(t.amount) > 10000 ORDER BY c.credit_score DESC LIMIT 5;",
            )

        # Turn 10: Full customer summary
        if "finally" in q_lower or ("credit score" in q_lower and "branch name" in q_lower):
            return TextToSQLRuntimeResponse.success(
                "SELECT c.customer_id, c.first_name, c.credit_score, a.balance, b.branch_name, t.total_amount FROM customers c JOIN accounts a ON c.customer_id = a.customer_id JOIN branches b ON a.branch_id = b.branch_id JOIN (SELECT account_id, SUM(amount) AS total_amount FROM transactions GROUP BY account_id) t ON a.account_id = t.account_id ORDER BY c.credit_score DESC LIMIT 5;",
            )

        return TextToSQLRuntimeResponse.success("SELECT 1;")

    # --------------------------------------------------------------------------
    # Turn 1: HIS-001 "Show all customers."
    # --------------------------------------------------------------------------
    d1 = router.route(
        "Show all customers.",
        conversation_id=conv_id,
        tenant_id=tenant_id,
        user_id=user_id,
        raw_conversation=tuple(conversation_history),
        executor=mock_backend_executor,
    )
    assert d1.route == ConversationRoute.NEW_DATABASE_QUERY
    assert d1.is_success is True
    assert "customers" in d1.generated_sql.lower()
    conversation_history.append({
        "role": "turn",
        "user_question": "Show all customers.",
        "generated_sql": d1.generated_sql,
        "execution_status": "Completed",
    })

    # --------------------------------------------------------------------------
    # Turn 2: HIS-002 "Now show only the top 5 customers by credit score."
    # --------------------------------------------------------------------------
    d2 = router.route(
        "Now show only the top 5 customers by credit score.",
        conversation_id=conv_id,
        tenant_id=tenant_id,
        user_id=user_id,
        raw_conversation=tuple(conversation_history),
        executor=mock_backend_executor,
    )
    assert d2.is_success is True
    assert "credit_score desc" in d2.generated_sql.lower()
    assert "limit 5" in d2.generated_sql.lower()
    conversation_history.append({
        "role": "turn",
        "user_question": "Now show only the top 5 customers by credit score.",
        "generated_sql": d2.generated_sql,
        "execution_status": "Completed",
    })

    state = router.state_manager.get_or_create_state(conv_id)
    assert state.last_successful_execution is not None
    assert "top 5 customers by credit score" in state.last_successful_execution.user_question.lower()

    # --------------------------------------------------------------------------
    # Turn 3: HIS-003 "Now show the phone numbers of those top 5 customers."
    # Schema validation rejection: phone_number does not exist in customers
    # --------------------------------------------------------------------------
    d3 = router.route(
        "Now show the phone numbers of those top 5 customers.",
        conversation_id=conv_id,
        tenant_id=tenant_id,
        user_id=user_id,
        raw_conversation=tuple(conversation_history),
        executor=mock_backend_executor,
    )
    assert d3.is_success is False
    assert d3.route in (ConversationRoute.EXECUTION_ERROR, ConversationRoute.FOLLOW_UP_QUERY)
    # Provenance check: Last successful execution must still be Turn 2!
    state = router.state_manager.get_or_create_state(conv_id)
    assert "top 5 customers by credit score" in state.last_successful_execution.user_question.lower()

    conversation_history.append({
        "role": "turn",
        "user_question": "Now show the phone numbers of those top 5 customers.",
        "execution_status": "Failed",
        "error": "Column 'customers.phone_number' not found in schema.",
    })

    # --------------------------------------------------------------------------
    # Turn 4: HIS-004 "Show the branch name for each of those customers using customers.branch_id."
    # Schema validation rejection: branch_id does not exist in customers
    # --------------------------------------------------------------------------
    d4 = router.route(
        "Show the branch name for each of those customers using customers.branch_id.",
        conversation_id=conv_id,
        tenant_id=tenant_id,
        user_id=user_id,
        raw_conversation=tuple(conversation_history),
        executor=mock_backend_executor,
    )
    assert d4.is_success is False
    # Provenance check: Last successful execution must still be Turn 2!
    state = router.state_manager.get_or_create_state(conv_id)
    assert "top 5 customers by credit score" in state.last_successful_execution.user_question.lower()

    conversation_history.append({
        "role": "turn",
        "user_question": "Show the branch name for each of those customers using customers.branch_id.",
        "execution_status": "Failed",
        "error": "Column 'customers.branch_id' not found in schema.",
    })

    # --------------------------------------------------------------------------
    # Turn 5: HIS-005 "Go back to the top 5 customers from before and show their account balances."
    # Must resolve scope back to Turn 2 ("top 5 customers by credit score")
    # --------------------------------------------------------------------------
    d5 = router.route(
        "Go back to the top 5 customers from before and show their account balances.",
        conversation_id=conv_id,
        tenant_id=tenant_id,
        user_id=user_id,
        raw_conversation=tuple(conversation_history),
        executor=mock_backend_executor,
    )
    assert d5.route == ConversationRoute.FOLLOW_UP_QUERY
    assert d5.is_success is True
    # The resolved question MUST reference the top 5 customers by credit score!
    assert "top 5 customers by credit score" in d5.resolved_question.lower()
    assert "account balance" in d5.resolved_question.lower()
    # Generated SQL must join accounts and order by credit score!
    assert "accounts" in d5.generated_sql.lower()
    assert "credit_score desc" in d5.generated_sql.lower()

    conversation_history.append({
        "role": "turn",
        "user_question": d5.resolved_question,
        "generated_sql": d5.generated_sql,
        "execution_status": "Completed",
    })

    # --------------------------------------------------------------------------
    # Turn 6: HIS-006 "For those same customers, show their total transaction amount."
    # --------------------------------------------------------------------------
    d6 = router.route(
        "For those same customers, show their total transaction amount.",
        conversation_id=conv_id,
        tenant_id=tenant_id,
        user_id=user_id,
        raw_conversation=tuple(conversation_history),
        executor=mock_backend_executor,
    )
    assert d6.route == ConversationRoute.FOLLOW_UP_QUERY
    assert d6.is_success is True
    assert "top 5 customers by credit score" in d6.resolved_question.lower()
    assert "transaction" in d6.generated_sql.lower()

    summary_turn6 = "The total transaction amount for all customers is $9,854.12 across 149 transactions."
    result_meta_turn6 = ResultMetadata(
        columns=("customer_id", "first_name", "total_amount"),
        row_count=5,
        summary=summary_turn6,
    )
    state = router.state_manager.get_or_create_state(conv_id)
    state.last_result_metadata = result_meta_turn6

    conversation_history.append({
        "role": "turn",
        "user_question": d6.resolved_question,
        "generated_sql": d6.generated_sql,
        "execution_status": "Completed",
        "execution_result_summary": summary_turn6,
    })

    # --------------------------------------------------------------------------
    # Turn 7: HIS-007 "For those customers, show their transaction status."
    # ResultResolver must NOT hijack this into "Customers's value was $9."!
    # Text-to-SQL / Schema validation must reject nonexistent transactions.status
    # --------------------------------------------------------------------------
    d7 = router.route(
        "For those customers, show their transaction status.",
        conversation_id=conv_id,
        tenant_id=tenant_id,
        user_id=user_id,
        raw_conversation=tuple(conversation_history),
        last_result_metadata={"summary": summary_turn6, "columns": ["customer_id", "first_name", "total_amount"]},
        executor=mock_backend_executor,
    )
    # Must NOT be RESULT_ANSWER
    assert d7.route != ConversationRoute.RESULT_ANSWER
    # Must be an execution rejection
    assert d7.is_success is False
    assert "status" in d7.error_message.lower()

    conversation_history.append({
        "role": "turn",
        "user_question": "For those customers, show their transaction status.",
        "execution_status": "Failed",
        "error": "Column 'transactions.status' not found in schema.",
    })

    # --------------------------------------------------------------------------
    # Turn 8: HIS-008 "Now show only customers whose total transaction amount is greater than 10,000 USD."
    # ResultResolver must NOT hijack this!
    # Follow-up filtering on top 5 customers by credit score
    # --------------------------------------------------------------------------
    d8 = router.route(
        "Now show only customers whose total transaction amount is greater than 10,000 USD.",
        conversation_id=conv_id,
        tenant_id=tenant_id,
        user_id=user_id,
        raw_conversation=tuple(conversation_history),
        executor=mock_backend_executor,
    )
    assert d8.route != ConversationRoute.RESULT_ANSWER
    assert d8.is_success is True
    assert "top 5 customers by credit score" in d8.resolved_question.lower()
    assert "10,000" in d8.resolved_question or "10000" in d8.resolved_question

    conversation_history.append({
        "role": "turn",
        "user_question": d8.resolved_question,
        "generated_sql": d8.generated_sql,
        "execution_status": "Completed",
    })

    # --------------------------------------------------------------------------
    # Turn 9: HIS-009 "For the customers above, show their preferred branch using preferred_branch_id."
    # ResultResolver must NOT match "branch" to customer Larry Branch!
    # Rejected by schema validator because preferred_branch_id does not exist
    # --------------------------------------------------------------------------
    sample_rows_turn8 = (
        ("CUS1", "Alex", "Smith", 750),
        ("CUS2", "Larry", "Branch", 740),
    )
    d9 = router.route(
        "For the customers above, show their preferred branch using preferred_branch_id.",
        conversation_id=conv_id,
        tenant_id=tenant_id,
        user_id=user_id,
        raw_conversation=tuple(conversation_history),
        last_result_metadata={
            "columns": ["customer_id", "first_name", "last_name", "credit_score"],
            "sample_rows": sample_rows_turn8,
            "row_count": 2,
        },
        executor=mock_backend_executor,
    )
    # Must NOT return Larry Branch as a direct answer
    assert d9.route != ConversationRoute.RESULT_ANSWER
    assert d9.is_success is False
    assert "preferred_branch_id" in d9.error_message.lower()

    conversation_history.append({
        "role": "turn",
        "user_question": "For the customers above, show their preferred branch using preferred_branch_id.",
        "execution_status": "Failed",
        "error": "Column 'preferred_branch_id' not found in schema.",
    })

    # --------------------------------------------------------------------------
    # Turn 10: HIS-010 "Finally, show the customer name, credit score, total balance, branch name, and total transaction amount for the same customers."
    # Must resolve scope to the same top 5 customers by credit score
    # --------------------------------------------------------------------------
    d10 = router.route(
        "Finally, show the customer name, credit score, total balance, branch name, and total transaction amount for the same customers.",
        conversation_id=conv_id,
        tenant_id=tenant_id,
        user_id=user_id,
        raw_conversation=tuple(conversation_history),
        executor=mock_backend_executor,
    )
    assert d10.route != ConversationRoute.RESULT_ANSWER
    assert d10.is_success is True
    assert "top 5 customers by credit score" in d10.resolved_question.lower()
    assert "branches" in d10.generated_sql.lower() or "branch_name" in d10.generated_sql.lower()


def test_domain_agnostic_scope_extraction():
    """Verify that entity scope extraction works uniformly across varied domains without hardcoding."""
    resolver = ContinuationResolver()

    # Healthcare domain
    scope_health = resolver._extract_base_entity_scope("Show all patients admitted to oncology.")
    assert scope_health == "all patients admitted to oncology"

    # E-commerce domain
    scope_ecom = resolver._extract_base_entity_scope("Now show only the top 10 products by revenue.")
    assert scope_ecom == "the top 10 products by revenue"

    # Logistics domain
    scope_logistics = resolver._extract_base_entity_scope("List active shipments from warehouse Alpha.")
    assert scope_logistics == "active shipments from warehouse Alpha"

    # Resolving pronoun reference with established scope in healthcare
    res_health = resolver.resolve(
        "For those same patients, show their prescribed medications.",
        state=None,
        followup=FollowupDetector().detect("For those same patients, show their prescribed medications.", has_history=True),
        prior_question="Show all patients admitted to oncology.",
    )
    assert res_health.is_resolved is True
    assert "all patients admitted to oncology" in res_health.resolved_question.lower()
    assert "prescribed medications" in res_health.resolved_question.lower()


def test_result_resolver_strictly_rejects_database_queries_across_verbs():
    """Verify that database query commands are NEVER answered from metadata or cell lookup."""
    resolver = ResultResolver()
    metadata = ResultMetadata(
        columns=("customer_id", "first_name", "last_name", "branch"),
        row_count=5,
        summary="The total count for customers in branch North is 5.",
        sample_rows=(("C1", "Larry", "Branch", "North"),),
    )

    query_commands = [
        "Show their account balances.",
        "List all transactions.",
        "For those customers, show their status.",
        "Now show only customers whose total > 1000.",
        "Display their preferred branch.",
        "Find the average transaction amount.",
        "Get all orders for the same customers.",
        "Go back to the top 5 customers from before.",
    ]

    for q in query_commands:
        outcome = resolver.resolve(q, metadata, summary=metadata.summary)
        assert outcome.status == ResultResolutionStatus.NOT_ANSWERABLE, f"Query '{q}' was erroneously hijacked by ResultResolver!"
