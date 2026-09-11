"""End-to-End Adversarial Pipeline Test Suite for CopilotRuntimePipeline.

Exercises the full orchestration path for scenarios E2E-1 through E2E-11:
- E2E-1 Basic valid query (Show all customer balances)
- E2E-2 Aggregation (What is the total transaction volume?)
- E2E-3 Distinct count (How many customers are there?)
- E2E-4 Multi-table join (Show transactions with customer information)
- E2E-5 Fanout isolation (Customers with transaction volume and loan exposure)
- E2E-6 Branch security (Show accounts for my branch)
- E2E-7 Clarification (needs_clarification -> zero SQL validation/execution)
- E2E-8 Unsafe request (unsafe_request -> typed rejection)
- E2E-9 Oscillation (A -> B -> A -> immediate early abort)
- E2E-10 Multi-statement (SELECT ...; SELECT ...; independent validation)
- E2E-11 Piggyback (SELECT ...; DROP TABLE accounts; entire batch rejection)
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.self_correction.critic_result import CriticIssue, CriticResult
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import (
    CopilotRuntimePipeline,
)
from src.application.services.self_correction.critic_finding_verifier import (
    CriticFindingVerifier,
)
from src.application.services.self_correction.self_correction_service import (
    SelfCorrectionService,
)
from src.application.services.self_correction.sql_deterministic_repair_service import (
    SQLDeterministicRepairService,
)
from src.application.services.self_correction.validators.sql_relationship_validator import (
    SQLRelationshipValidator,
)
from src.application.services.self_correction.validators.sql_rls_validator import (
    SQLRlsValidator,
)
from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)


class AuthoritativeSchema:
    def get_schema(self) -> dict[str, Any]:
        return {
            "tables": {
                "branches": {
                    "columns": [
                        {"name": "branch_id", "type": "int"},
                        {"name": "branch_name", "type": "nvarchar"},
                    ]
                },
                "accounts": {
                    "columns": [
                        {"name": "account_id", "type": "int"},
                        {"name": "branch_id", "type": "int"},
                        {"name": "customer_id", "type": "int"},
                        {"name": "balance_usd", "type": "decimal"},
                    ]
                },
                "customers": {
                    "columns": [
                        {"name": "customer_id", "type": "int"},
                        {"name": "first_name", "type": "nvarchar"},
                        {"name": "last_name", "type": "nvarchar"},
                    ]
                },
                "transactions": {
                    "columns": [
                        {"name": "transaction_id", "type": "int"},
                        {"name": "account_id", "type": "int"},
                        {"name": "amount_usd", "type": "decimal"},
                    ]
                },
                "loans": {
                    "columns": [
                        {"name": "loan_id", "type": "int"},
                        {"name": "customer_id", "type": "int"},
                        {"name": "loan_amount_usd", "type": "decimal"},
                    ]
                },
            },
            "relationships": [
                {"from_table": "branches", "from_column": "branch_id", "to_table": "accounts", "to_column": "branch_id"},
                {"from_table": "customers", "from_column": "customer_id", "to_table": "accounts", "to_column": "customer_id"},
                {"from_table": "accounts", "from_column": "account_id", "to_table": "transactions", "to_column": "account_id"},
                {"from_table": "customers", "from_column": "customer_id", "to_table": "loans", "to_column": "customer_id"},
            ],
        }


def _create_e2e_pipeline(mock_model_output: str | dict, mock_critic: Any = None, mock_correction: Any = None):
    schema_repo = AuthoritativeSchema()
    syntax = SQLSyntaxValidator()
    schema = SQLSchemaValidator(schema_repo, syntax)
    rel = SQLRelationshipValidator(None, syntax, schema)
    rls = SQLRlsValidator(syntax, schema)
    repair = SQLDeterministicRepairService(syntax, schema, rls)
    verifier = CriticFindingVerifier(schema_repo)

    text_to_sql = MagicMock()
    text_to_sql.build_context.return_value = "### Schema\nTables: branches, accounts, customers, transactions, loans"
    mock_gen = MagicMock()
    mock_gen.text = json.dumps(mock_model_output) if isinstance(mock_model_output, dict) else mock_model_output
    text_to_sql.run.return_value = mock_gen

    critic = mock_critic or MagicMock()
    if not mock_critic:
        critic.evaluate.return_value = CriticResult("PASS")

    correction = mock_correction or MagicMock()

    context = MagicMock()
    context.build_llm_context.return_value = "### Context"

    self_corr = SelfCorrectionService(
        context_retrieval_service=context,
        syntax_validator=syntax,
        schema_validator=schema,
        relationship_validator=rel,
        critic_service=critic,
        finding_verifier=verifier,
        correction_service=correction,
        max_attempts=3,
        rls_validator=rls,
        schema_provider=schema_repo,
        repair_service=repair,
    )

    pipeline = CopilotRuntimePipeline(text_to_sql, self_corr)
    return pipeline, text_to_sql, critic, correction


def test_e2e_1_basic_valid_query():
    """E2E-1: Show all customer balances."""
    sql = (
        "SELECT c.customer_id, c.first_name, a.balance_usd "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE a.branch_id = @UserBranchId"
    )
    pipeline, text_to_sql, critic, correction = _create_e2e_pipeline({
        "status": "success", "sql": sql, "is_read_only": True
    })

    resp = pipeline.run(CopilotAskRequest(question="Show all customer balances", conversation=()))
    assert resp.status == "Success"
    assert resp.sql is not None
    assert "@UserBranchId" in resp.sql
    correction.correct.assert_not_called()


def test_e2e_2_aggregation_transaction_volume():
    """E2E-2: What is the total transaction volume?"""
    sql = (
        "SELECT SUM(t.amount_usd) AS total_transaction_volume "
        "FROM transactions AS t "
        "INNER JOIN accounts AS a ON t.account_id = a.account_id "
        "WHERE a.branch_id = @UserBranchId"
    )
    pipeline, _, _, _ = _create_e2e_pipeline({
        "status": "success", "sql": sql, "is_read_only": True
    })

    resp = pipeline.run(CopilotAskRequest(question="What is the total transaction volume?", conversation=()))
    assert resp.status == "Success"
    assert "SUM(t.amount_usd)" in resp.sql or "SUM(t.amount_usd)" in resp.sql.replace(" ", "")


def test_e2e_3_distinct_count_customers():
    """E2E-3: How many customers are there?"""
    sql = (
        "SELECT COUNT(DISTINCT c.customer_id) AS total_customers "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE a.branch_id = @UserBranchId"
    )
    pipeline, _, _, _ = _create_e2e_pipeline({
        "status": "success", "sql": sql, "is_read_only": True
    })

    resp = pipeline.run(CopilotAskRequest(question="How many customers are there?", conversation=()))
    assert resp.status == "Success"
    assert "COUNT(DISTINCT" in resp.sql.replace(" ", "").upper()


def test_e2e_4_multi_table_join():
    """E2E-4: Show transactions with customer information (customers -> accounts -> transactions)."""
    sql = (
        "SELECT c.first_name, c.last_name, t.transaction_id, t.amount_usd "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "INNER JOIN transactions AS t ON a.account_id = t.account_id "
        "WHERE a.branch_id = @UserBranchId"
    )
    pipeline, _, _, _ = _create_e2e_pipeline({
        "status": "success", "sql": sql, "is_read_only": True
    })

    resp = pipeline.run(CopilotAskRequest(question="Show transactions with customer information", conversation=()))
    assert resp.status == "Success"
    assert resp.sql is not None


def test_e2e_5_fanout_safe_aggregation():
    """E2E-5: Show customers with total transaction volume and loan exposure (CTE pre-aggregated)."""
    sql = (
        "WITH cust_tx AS ("
        "    SELECT a.customer_id, SUM(t.amount_usd) AS total_tx "
        "    FROM accounts AS a "
        "    INNER JOIN transactions AS t ON a.account_id = t.account_id "
        "    WHERE a.branch_id = @UserBranchId "
        "    GROUP BY a.customer_id"
        "), "
        "cust_loans AS ("
        "    SELECT l.customer_id, SUM(l.loan_amount_usd) AS total_loans "
        "    FROM loans AS l "
        "    GROUP BY l.customer_id"
        ") "
        "SELECT c.customer_id, c.first_name, "
        "COALESCE(ctx.total_tx, 0) AS total_tx, "
        "COALESCE(cln.total_loans, 0) AS total_loans "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "LEFT JOIN cust_tx AS ctx ON c.customer_id = ctx.customer_id "
        "LEFT JOIN cust_loans AS cln ON c.customer_id = cln.customer_id "
        "WHERE a.branch_id = @UserBranchId"
    )
    pipeline, _, _, _ = _create_e2e_pipeline({
        "status": "success", "sql": sql, "is_read_only": True
    })

    resp = pipeline.run(CopilotAskRequest(
        question="Show customers with their total transaction volume and loan exposure",
        conversation=()
    ))
    assert resp.status == "Success"
    assert "WITH" in resp.sql.upper()


def test_e2e_6_branch_security():
    """E2E-6: Show accounts for my branch."""
    sql = (
        "SELECT a.account_id, a.balance_usd "
        "FROM accounts AS a "
        "WHERE a.branch_id = @UserBranchId"
    )
    pipeline, _, _, _ = _create_e2e_pipeline({
        "status": "success", "sql": sql, "is_read_only": True
    })

    resp = pipeline.run(CopilotAskRequest(question="Show accounts for my branch", conversation=()))
    assert resp.status == "Success"
    assert "a.branch_id = @UserBranchId" in resp.sql


def test_e2e_7_clarification():
    """E2E-7: Model returns needs_clarification -> zero execution/validation."""
    pipeline, _, critic, correction = _create_e2e_pipeline({
        "status": "needs_clarification",
        "warnings": ["Which branch are you inquiring about?"]
    })

    resp = pipeline.run(CopilotAskRequest(question="Show branch metrics", conversation=()))
    assert resp.status == "Failed"
    assert resp.error_code == "NEEDS_CLARIFICATION"
    assert resp.sql is None
    critic.evaluate.assert_not_called()
    correction.correct.assert_not_called()


def test_e2e_8_unsafe_request():
    """E2E-8: Model returns unsafe_request -> typed rejection."""
    pipeline, _, critic, correction = _create_e2e_pipeline({
        "status": "unsafe_request",
        "warnings": ["Direct database configuration changes are forbidden."]
    })

    resp = pipeline.run(CopilotAskRequest(question="Inspect internal database credentials", conversation=()))
    assert resp.status == "Failed"
    assert resp.error_code == "UNSAFE_REQUEST"
    assert resp.sql is None


def test_e2e_9_oscillation_early_abort():
    """E2E-9: Alternating critic/correction A -> B -> A triggers immediate abort."""
    sql_a = "SELECT a.account_id FROM accounts AS a WHERE a.branch_id = @UserBranchId"
    sql_b = "SELECT a.account_id, a.balance_usd FROM accounts AS a WHERE a.branch_id = @UserBranchId"

    critic = MagicMock()
    critic.evaluate.side_effect = [
        CriticResult("FAIL", issues=(CriticIssue("INTENT", "Add balance", "accounts.balance_usd"),)),
        CriticResult("FAIL", issues=(CriticIssue("INTENT", "Remove balance", "accounts.balance_usd"),)),
        CriticResult("FAIL", issues=(CriticIssue("INTENT", "Add balance", "accounts.balance_usd"),)),
    ]

    correction = MagicMock()
    correction.correct.side_effect = [sql_b, sql_a, sql_b]

    pipeline, _, _, _ = _create_e2e_pipeline(
        {"status": "success", "sql": sql_a, "is_read_only": True},
        mock_critic=critic,
        mock_correction=correction,
    )

    resp = pipeline.run(CopilotAskRequest(question="Show accounts", conversation=()))
    assert resp.status == "Failed"
    assert resp.error_code == "CORRECTION_OSCILLATION"
    assert resp.sql is None


def test_e2e_10_multi_statement():
    """E2E-10: Multi-statement batch of valid SELECT queries passes."""
    multi_sql = (
        "SELECT a.account_id FROM accounts AS a WHERE a.branch_id = @UserBranchId;\n"
        "SELECT b.branch_id, b.branch_name FROM branches AS b WHERE b.branch_id = @UserBranchId"
    )
    pipeline, _, _, _ = _create_e2e_pipeline({
        "status": "success", "sql": multi_sql, "is_read_only": True
    })

    resp = pipeline.run(CopilotAskRequest(question="Show accounts and branches", conversation=()))
    assert resp.status == "Success"
    assert ";" in resp.sql


def test_e2e_11_piggyback_rejection():
    """E2E-11: Piggybacked destructive write in multi-statement query is rejected."""
    piggyback_sql = (
        "SELECT a.account_id FROM accounts AS a WHERE a.branch_id = @UserBranchId;\n"
        "DROP TABLE accounts;"
    )
    pipeline, _, _, _ = _create_e2e_pipeline({
        "status": "success", "sql": piggyback_sql, "is_read_only": True
    })

    resp = pipeline.run(CopilotAskRequest(question="Show accounts and audit logs", conversation=()))
    assert resp.status == "Failed"
    assert resp.error_code == "SQL_VALIDATION_FAILED"
    assert resp.sql is None
