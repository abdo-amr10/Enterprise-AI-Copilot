"""Comprehensive Execution-Grade Adversarial Audit Test Suite for AI / Text-to-SQL Execution Layer.

This test suite performs rigorous adversarial probing across:
1. RLS Equivalence (Cases A, B, C, D, E) & Ping-Pong Immunity
2. Deterministic AST Repair & Full Semantic Preservation
3. Fanout Aggregation & DISTINCT Semantics Protection
4. Self-Correction Oscillation & Canonical AST Fingerprinting
5. Typed Model Response Contract & Strict None-Safety
6. Multi-Statement Read-Only Validation & Piggybacked Command Defense
7. Independent Multi-Statement RLS Enforcement
8. End-to-End Orchestration & Truthful Tracing
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
import sqlglot
from sqlglot import exp

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
    compute_sql_fingerprint,
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


class AuthoritativeSchemaRepo:
    """Authoritative physical schema metadata matching docs/database_metadata/schema.json."""

    def get_schema(self) -> dict[str, Any]:
        return {
            "tables": {
                "branches": {
                    "columns": [
                        {"name": "branch_id", "type": "int"},
                        {"name": "branch_name", "type": "nvarchar"},
                        {"name": "city", "type": "nvarchar"},
                        {"name": "state", "type": "nvarchar"},
                    ]
                },
                "accounts": {
                    "columns": [
                        {"name": "account_id", "type": "int"},
                        {"name": "branch_id", "type": "int"},
                        {"name": "customer_id", "type": "int"},
                        {"name": "account_type", "type": "nvarchar"},
                        {"name": "balance_usd", "type": "decimal"},
                        {"name": "status", "type": "nvarchar"},
                    ]
                },
                "customers": {
                    "columns": [
                        {"name": "customer_id", "type": "int"},
                        {"name": "first_name", "type": "nvarchar"},
                        {"name": "last_name", "type": "nvarchar"},
                        {"name": "city", "type": "nvarchar"},
                        {"name": "state", "type": "nvarchar"},
                        {"name": "credit_score", "type": "int"},
                    ]
                },
                "transactions": {
                    "columns": [
                        {"name": "transaction_id", "type": "int"},
                        {"name": "account_id", "type": "int"},
                        {"name": "merchant_id", "type": "int"},
                        {"name": "amount_usd", "type": "decimal"},
                        {"name": "transaction_type", "type": "nvarchar"},
                        {"name": "transaction_date", "type": "datetime"},
                    ]
                },
                "cards": {
                    "columns": [
                        {"name": "card_id", "type": "int"},
                        {"name": "account_id", "type": "int"},
                        {"name": "card_number", "type": "nvarchar"},
                        {"name": "card_type", "type": "nvarchar"},
                    ]
                },
                "loans": {
                    "columns": [
                        {"name": "loan_id", "type": "int"},
                        {"name": "customer_id", "type": "int"},
                        {"name": "loan_amount_usd", "type": "decimal"},
                        {"name": "loan_status", "type": "nvarchar"},
                    ]
                },
                "merchants": {
                    "columns": [
                        {"name": "merchant_id", "type": "int"},
                        {"name": "merchant_name", "type": "nvarchar"},
                        {"name": "merchant_category", "type": "nvarchar"},
                    ]
                },
            },
            "relationships": [
                {
                    "from_table": "branches",
                    "from_column": "branch_id",
                    "to_table": "accounts",
                    "to_column": "branch_id",
                },
                {
                    "from_table": "customers",
                    "from_column": "customer_id",
                    "to_table": "accounts",
                    "to_column": "customer_id",
                },
                {
                    "from_table": "accounts",
                    "from_column": "account_id",
                    "to_table": "transactions",
                    "to_column": "account_id",
                },
                {
                    "from_table": "accounts",
                    "from_column": "account_id",
                    "to_table": "cards",
                    "to_column": "account_id",
                },
                {
                    "from_table": "customers",
                    "from_column": "customer_id",
                    "to_table": "loans",
                    "to_column": "customer_id",
                },
                {
                    "from_table": "merchants",
                    "from_column": "merchant_id",
                    "to_table": "transactions",
                    "to_column": "merchant_id",
                },
            ],
            "security_domains": [
                {
                    "name": "branch",
                    "canonical_root": "accounts.branch_id",
                    "canonical_predicate": "accounts.branch_id = @UserBranchId",
                    "propagation_paths": [
                        {
                            "target_table": "accounts",
                            "path": "accounts.branch_id = @UserBranchId",
                            "propagation": "allowed",
                            "is_canonical_root": True,
                        },
                        {
                            "target_table": "branches",
                            "path": "branches.branch_id = @UserBranchId",
                            "propagation": "allowed",
                            "predicate_equivalence": {"INNER JOIN": True, "LEFT JOIN": "conditional", "RIGHT JOIN": "conditional", "FULL JOIN": False},
                        },
                        {
                            "target_table": "transactions",
                            "path": "transactions.account_id = accounts.account_id -> accounts.branch_id = @UserBranchId",
                            "propagation": "allowed",
                        },
                        {
                            "target_table": "cards",
                            "path": "cards.account_id = accounts.account_id -> accounts.branch_id = @UserBranchId",
                            "propagation": "allowed",
                        },
                        {
                            "target_table": "customers",
                            "path": "customers.customer_id = accounts.customer_id -> accounts.branch_id = @UserBranchId",
                            "propagation": "allowed",
                        },
                        {
                            "target_table": "loans",
                            "path": "loans.customer_id = customers.customer_id -> customers.customer_id = accounts.customer_id -> branches.branch_id = @UserBranchId",
                            "propagation": "allowed",
                            "predicate_equivalence": {"INNER JOIN": True},
                        },
                        {
                            "target_table": "merchants",
                            "path": "merchants.merchant_id = transactions.merchant_id -> transactions.account_id = accounts.account_id -> accounts.branch_id = @UserBranchId",
                            "propagation": "allowed",
                        },
                    ],
                }
            ],
        }


def _create_harness():
    syntax = SQLSyntaxValidator()
    schema_repo = AuthoritativeSchemaRepo()
    schema = SQLSchemaValidator(schema_repo, syntax)
    rel = SQLRelationshipValidator(None, syntax, schema)
    rls = SQLRlsValidator(syntax, schema)
    repair = SQLDeterministicRepairService(syntax, schema, rls)
    return syntax, schema, rel, rls, repair, schema_repo


# ==============================================================================
# 1. RLS EQUIVALENCE & JOIN-TYPE SAFETY AUDIT (Cases A, B, C, D, E)
# ==============================================================================

def test_adversarial_rls_case_a_inner_join_branches_to_accounts():
    """Case A: INNER JOIN between branches and accounts filtered on branches.branch_id."""
    syntax, schema, rel, rls, _, schema_repo = _create_harness()
    sql = (
        "SELECT b.branch_id, b.branch_name, a.balance_usd "
        "FROM branches AS b "
        "INNER JOIN accounts AS a ON b.branch_id = a.branch_id "
        "WHERE b.branch_id = @UserBranchId"
    )
    res = rls.validate(sql, schema=schema_repo.get_schema(), enforce_presence=True)
    assert res.is_valid, f"Case A failed: {res.issues}"


def test_adversarial_rls_case_b_inner_join_accounts_to_branches():
    """Case B: INNER JOIN between branches and accounts filtered on accounts.branch_id."""
    syntax, schema, rel, rls, _, schema_repo = _create_harness()
    sql = (
        "SELECT b.branch_id, b.branch_name, a.balance_usd "
        "FROM branches AS b "
        "INNER JOIN accounts AS a ON b.branch_id = a.branch_id "
        "WHERE a.branch_id = @UserBranchId"
    )
    res = rls.validate(sql, schema=schema_repo.get_schema(), enforce_presence=True)
    assert res.is_valid, f"Case B failed: {res.issues}"


def test_adversarial_rls_case_c_left_join_non_equivalence():
    """Case C: LEFT JOIN does NOT establish unconditional equivalence for the primary accounts table."""
    syntax, schema, rel, rls, _, schema_repo = _create_harness()
    sql = (
        "SELECT a.account_id, b.branch_name "
        "FROM accounts AS a "
        "LEFT JOIN branches AS b ON a.branch_id = b.branch_id "
        "WHERE b.branch_id = @UserBranchId"
    )
    res = rls.validate(sql, schema=schema_repo.get_schema(), enforce_presence=True)
    assert not res.is_valid, "Case C should reject LEFT JOIN unconditional equivalence"


def test_adversarial_rls_case_d_full_join_non_equivalence():
    """Case D: FULL JOIN does NOT establish unconditional equivalence."""
    syntax, schema, rel, rls, _, schema_repo = _create_harness()
    sql = (
        "SELECT a.account_id, b.branch_name "
        "FROM accounts AS a "
        "FULL JOIN branches AS b ON a.branch_id = b.branch_id "
        "WHERE b.branch_id = @UserBranchId"
    )
    res = rls.validate(sql, schema=schema_repo.get_schema(), enforce_presence=True)
    assert not res.is_valid, "Case D should reject FULL JOIN unconditional equivalence"


def test_adversarial_rls_case_e_cross_join_non_equivalence():
    """Case E: CROSS JOIN does NOT establish unconditional equivalence."""
    syntax, schema, rel, rls, _, schema_repo = _create_harness()
    sql = (
        "SELECT a.account_id, b.branch_name "
        "FROM accounts AS a "
        "CROSS JOIN branches AS b "
        "WHERE b.branch_id = @UserBranchId"
    )
    res = rls.validate(sql, schema=schema_repo.get_schema(), enforce_presence=True)
    assert not res.is_valid, "Case E should reject CROSS JOIN unconditional equivalence"


def test_adversarial_rls_no_ping_pong_between_valid_predicates():
    """Verify that neither Case A nor Case B triggers self-correction or repairs unnecessarily."""
    syntax, schema, rel, rls, repair, schema_repo = _create_harness()
    sql_a = (
        "SELECT b.branch_id, b.branch_name, a.balance_usd "
        "FROM branches AS b "
        "INNER JOIN accounts AS a ON b.branch_id = a.branch_id "
        "WHERE b.branch_id = @UserBranchId"
    )
    sql_b = (
        "SELECT b.branch_id, b.branch_name, a.balance_usd "
        "FROM branches AS b "
        "INNER JOIN accounts AS a ON b.branch_id = a.branch_id "
        "WHERE a.branch_id = @UserBranchId"
    )

    repaired_a = repair.repair(sql_a, schema=schema_repo.get_schema(), enforce_rls=True)
    repaired_b = repair.repair(sql_b, schema=schema_repo.get_schema(), enforce_rls=True)

    # Both must pass without altering valid predicates or creating ping-pong
    assert rls.validate(repaired_a, schema=schema_repo.get_schema(), enforce_presence=True).is_valid
    assert rls.validate(repaired_b, schema=schema_repo.get_schema(), enforce_presence=True).is_valid


# ==============================================================================
# 2. DETERMINISTIC AST REPAIR & SEMANTIC PRESERVATION AUDIT
# ==============================================================================

def test_adversarial_repair_preserves_complex_projections_and_aliases():
    """Repair must preserve computed projections, mathematical operators, and aliases."""
    syntax, schema, rel, rls, repair, schema_repo = _create_harness()
    sql = (
        "SELECT a.account_id, (a.balance_usd * 1.05) AS adjusted_balance, "
        "UPPER(a.account_type) AS type_label "
        "FROM accounts AS a "
        "WHERE a.branch_id = @UserBranchId AND a.balance_usd > 500"
    )
    repaired = repair.repair(sql, schema=schema_repo.get_schema(), enforce_rls=True)

    tree = syntax.parse(repaired)
    proj_sql = [p.sql(dialect="tsql") for p in tree.expressions]
    assert any("adjusted_balance" in p for p in proj_sql)
    assert any("type_label" in p for p in proj_sql)
    assert "@UserBranchId" in repaired
    assert rls.validate(repaired, schema=schema_repo.get_schema(), enforce_presence=True).is_valid


def test_adversarial_repair_preserves_group_by_and_having():
    """Repair must preserve GROUP BY columns and HAVING aggregate conditions."""
    syntax, schema, rel, rls, repair, schema_repo = _create_harness()
    sql = (
        "SELECT a.account_type, COUNT(a.account_id) AS total_accs, SUM(a.balance_usd) AS total_bal "
        "FROM accounts AS a "
        "WHERE a.branch_id = @UserBranchId "
        "GROUP BY a.account_type "
        "HAVING SUM(a.balance_usd) > 100000"
    )
    repaired = repair.repair(sql, schema=schema_repo.get_schema(), enforce_rls=True)

    tree = syntax.parse(repaired)
    assert tree.args.get("group") is not None
    assert tree.args.get("having") is not None
    assert "100000" in tree.args.get("having").sql()
    assert rls.validate(repaired, schema=schema_repo.get_schema(), enforce_presence=True).is_valid


def test_adversarial_repair_preserves_order_by_and_limit():
    """Repair must preserve ORDER BY expressions and TOP/LIMIT expressions."""
    syntax, schema, rel, rls, repair, schema_repo = _create_harness()
    sql = (
        "SELECT TOP 10 a.account_id, a.balance_usd "
        "FROM accounts AS a "
        "WHERE a.branch_id = @UserBranchId "
        "ORDER BY a.balance_usd DESC"
    )
    repaired = repair.repair(sql, schema=schema_repo.get_schema(), enforce_rls=True)

    tree = syntax.parse(repaired)
    assert tree.args.get("order") is not None
    assert "DESC" in tree.args.get("order").sql().upper()
    assert syntax.validate(repaired).is_valid
    assert rls.validate(repaired, schema=schema_repo.get_schema(), enforce_presence=True).is_valid


def test_adversarial_repair_preserves_cte_structure():
    """Repair must preserve CTE definitions without mangling WITH clauses."""
    syntax, schema, rel, rls, repair, schema_repo = _create_harness()
    sql = (
        "WITH high_balance_accounts AS ("
        "    SELECT a.account_id, a.customer_id, a.balance_usd "
        "    FROM accounts AS a "
        "    WHERE a.balance_usd > 50000 AND a.branch_id = @UserBranchId"
        ") "
        "SELECT c.customer_id, c.first_name, hba.balance_usd "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "INNER JOIN high_balance_accounts AS hba ON c.customer_id = hba.customer_id "
        "WHERE a.branch_id = @UserBranchId"
    )
    repaired = repair.repair(sql, schema=schema_repo.get_schema(), enforce_rls=True)
    tree = syntax.parse(repaired)
    assert any(tree.find_all(exp.CTE))
    assert rls.validate(repaired, schema=schema_repo.get_schema(), enforce_presence=True).is_valid


def test_adversarial_repair_idempotency_triple_pass():
    """repair(repair(repair(sql))) must be identically equal on normalized AST."""
    syntax, schema, rel, rls, repair, schema_repo = _create_harness()
    raw_sql = (
        "SELECT c.customer_id, c.first_name, c.credit_score "
        "FROM customers AS c "
        "WHERE c.credit_score >= 650"
    )
    pass1 = repair.repair(raw_sql, schema=schema_repo.get_schema(), enforce_rls=True)
    pass2 = repair.repair(pass1, schema=schema_repo.get_schema(), enforce_rls=True)
    pass3 = repair.repair(pass2, schema=schema_repo.get_schema(), enforce_rls=True)

    fp1 = compute_sql_fingerprint(pass1)
    fp2 = compute_sql_fingerprint(pass2)
    fp3 = compute_sql_fingerprint(pass3)
    assert fp1 == fp2 == fp3, f"Non-idempotent repair:\nPass 1: {pass1}\nPass 2: {pass2}\nPass 3: {pass3}"


# ==============================================================================
# 3. FANOUT AGGREGATION & DISTINCT SEMANTICS AUDIT
# ==============================================================================

def test_adversarial_fanout_distinct_count_never_stripped_by_critic():
    """Critic attempting to strip COUNT(DISTINCT customer_id) must be filtered by verifier."""
    _, _, _, _, _, schema_repo = _create_harness()
    verifier = CriticFindingVerifier(schema_repo)

    hallucinated_finding = CriticResult(
        status="FAIL",
        issues=(
            CriticIssue(
                type="INTENT",
                description="Do not use distinct in COUNT(DISTINCT customer_id), use regular COUNT(customer_id) instead.",
                evidence="COUNT(DISTINCT customer_id)",
            ),
        ),
    )

    sql = (
        "SELECT COUNT(DISTINCT c.customer_id) AS total_customers "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE a.branch_id = @UserBranchId"
    )
    verified = verifier.verify(hallucinated_finding, schema=schema_repo.get_schema(), sql=sql)
    assert len(verified) == 0, f"Verifier failed to filter distinct removal attempt: {verified}"


def test_adversarial_fanout_multi_path_isolation():
    """Verify distinct parent count remains distinct when joining multiple child paths."""
    syntax, schema, rel, rls, repair, schema_repo = _create_harness()
    sql = (
        "SELECT COUNT(DISTINCT c.customer_id) AS active_customer_count "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "INNER JOIN transactions AS t ON a.account_id = t.account_id "
        "WHERE a.branch_id = @UserBranchId"
    )
    repaired = repair.repair(sql, schema=schema_repo.get_schema(), enforce_rls=True)
    assert "COUNT(DISTINCT" in repaired.replace(" ", "").upper()
    assert rls.validate(repaired, schema=schema_repo.get_schema(), enforce_presence=True).is_valid


# ==============================================================================
# 4. SELF-CORRECTION OSCILLATION & FINGERPRINTING AUDIT
# ==============================================================================

def test_adversarial_oscillation_abort_a_b_a():
    """Simulated A -> B -> A alternating loop must terminate immediately at attempt 2."""
    syntax, schema, rel, rls, repair, schema_repo = _create_harness()
    context = MagicMock()
    context.build_llm_context.return_value = "context"

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

    service = SelfCorrectionService(
        context_retrieval_service=context,
        syntax_validator=syntax,
        schema_validator=schema,
        relationship_validator=rel,
        critic_service=critic,
        finding_verifier=CriticFindingVerifier(schema_repo),
        correction_service=correction,
        max_attempts=5,
        rls_validator=rls,
        schema_provider=schema_repo,
        repair_service=repair,
    )

    steps = []
    outcome = service.run("Show accounts", sql_a, trace_observer=steps.append, enforce_rls=True)

    assert not outcome.is_valid
    assert any("CORRECTION_OSCILLATION" in i for i in outcome.issues)
    # Oscillation detected at attempt 2 -> stops immediately without exhausting all 5 attempts
    assert outcome.attempts_used == 2
    assert len(correction.correct.mock_calls) == 2
    assert len(steps) == 5


def test_adversarial_oscillation_abort_a_a_stagnant():
    """Simulated A -> A repeat must terminate immediately without extra attempts."""
    syntax, schema, rel, rls, repair, schema_repo = _create_harness()
    context = MagicMock()
    context.build_llm_context.return_value = "context"

    sql_a = "SELECT a.account_id FROM accounts AS a WHERE a.branch_id = @UserBranchId"

    critic = MagicMock()
    critic.evaluate.return_value = CriticResult(
        "FAIL", issues=(CriticIssue("INTENT", "Missing something", "accounts.account_id"),)
    )

    correction = MagicMock()
    # Model returns the exact same SQL
    correction.correct.return_value = sql_a

    service = SelfCorrectionService(
        context_retrieval_service=context,
        syntax_validator=syntax,
        schema_validator=schema,
        relationship_validator=rel,
        critic_service=critic,
        finding_verifier=CriticFindingVerifier(schema_repo),
        correction_service=correction,
        max_attempts=4,
        rls_validator=rls,
        schema_provider=schema_repo,
        repair_service=repair,
    )

    outcome = service.run("Show accounts", sql_a, enforce_rls=True)
    assert not outcome.is_valid
    assert any("CORRECTION_OSCILLATION" in i for i in outcome.issues)
    assert outcome.attempts_used <= 1


def test_adversarial_oscillation_whitespace_and_casing_insensitivity():
    """Fingerprint must treat whitespace and keyword casing as semantically identical."""
    sql1 = "SELECT a.account_id FROM accounts AS a WHERE a.branch_id = @UserBranchId"
    sql2 = "  select   a.account_id \n FROM \t accounts as a \n WHERE a.branch_id = @UserBranchId ; "
    fp1 = compute_sql_fingerprint(sql1)
    fp2 = compute_sql_fingerprint(sql2)
    assert fp1 == fp2, "Fingerprinting was fooled by whitespace or casing!"


def test_adversarial_correction_progression_a_b_c():
    """Genuinely new candidates A -> B -> C proceed normally until pass or max attempts."""
    syntax, schema, rel, rls, repair, schema_repo = _create_harness()
    context = MagicMock()
    context.build_llm_context.return_value = "context"

    sql_a = "SELECT a.account_id FROM accounts AS a WHERE a.branch_id = @UserBranchId"
    sql_b = "SELECT a.account_id, a.balance_usd FROM accounts AS a WHERE a.branch_id = @UserBranchId"
    sql_c = "SELECT a.account_id, a.balance_usd, a.account_type FROM accounts AS a WHERE a.branch_id = @UserBranchId"

    critic = MagicMock()
    critic.evaluate.side_effect = [
        CriticResult("FAIL", issues=(CriticIssue("INTENT", "Add balance", "accounts.balance_usd"),)),
        CriticResult("FAIL", issues=(CriticIssue("INTENT", "Add type", "accounts.account_type"),)),
        CriticResult("PASS"),
    ]

    correction = MagicMock()
    correction.correct.side_effect = [sql_b, sql_c]

    service = SelfCorrectionService(
        context_retrieval_service=context,
        syntax_validator=syntax,
        schema_validator=schema,
        relationship_validator=rel,
        critic_service=critic,
        finding_verifier=CriticFindingVerifier(schema_repo),
        correction_service=correction,
        max_attempts=3,
        rls_validator=rls,
        schema_provider=schema_repo,
        repair_service=repair,
    )

    outcome = service.run("Show accounts", sql_a, enforce_rls=True)
    assert outcome.is_valid
    assert outcome.sql == sql_c
    assert outcome.attempts_used == 2


# ==============================================================================
# 5. TYPED MODEL RESPONSE CONTRACT & STRICT NONE-SAFETY AUDIT
# ==============================================================================

def test_adversarial_typed_response_needs_clarification_zero_execution():
    """needs_clarification must bypass validation and correction completely."""
    text_to_sql = MagicMock()
    text_to_sql.build_context.return_value = "context"
    mock_gen = MagicMock()
    mock_gen.text = json.dumps({
        "status": "needs_clarification",
        "warnings": ["Which branch or date range are you asking about?"]
    })
    text_to_sql.run.return_value = mock_gen

    self_corr = MagicMock()
    pipeline = CopilotRuntimePipeline(text_to_sql, self_corr)

    resp = pipeline.run(CopilotAskRequest(question="Give me transaction summary", conversation=()))
    assert resp.status == "Failed"
    assert resp.error_code == "NEEDS_CLARIFICATION"
    assert resp.sql is None
    assert "date range" in resp.failure_reason
    self_corr.run.assert_not_called()


def test_adversarial_typed_response_unsafe_request():
    """unsafe_request must return typed rejection with no correction loop."""
    text_to_sql = MagicMock()
    text_to_sql.build_context.return_value = "context"
    mock_gen = MagicMock()
    mock_gen.text = json.dumps({
        "status": "unsafe_request",
        "warnings": ["Database shutdown operation not permitted."]
    })
    text_to_sql.run.return_value = mock_gen

    self_corr = MagicMock()
    pipeline = CopilotRuntimePipeline(text_to_sql, self_corr)

    resp = pipeline.run(CopilotAskRequest(question="Shutdown server", conversation=()))
    assert resp.status == "Failed"
    assert resp.error_code == "UNSAFE_REQUEST"
    assert resp.sql is None
    self_corr.run.assert_not_called()


def test_adversarial_typed_response_null_sql_strict_none_safety():
    """null sql field in success JSON must not cause AttributeError or unhandled exception."""
    text_to_sql = MagicMock()
    text_to_sql.build_context.return_value = "context"
    mock_gen = MagicMock()
    mock_gen.text = json.dumps({
        "status": "success",
        "sql": None,
        "is_read_only": True
    })
    text_to_sql.run.return_value = mock_gen

    self_corr = MagicMock()
    pipeline = CopilotRuntimePipeline(text_to_sql, self_corr)

    resp = pipeline.run(CopilotAskRequest(question="Show accounts", conversation=()))
    assert resp.status == "Failed"
    assert resp.error_code == "INVALID_MODEL_OUTPUT"
    assert resp.sql is None
    self_corr.run.assert_not_called()


def test_adversarial_typed_response_empty_string_sql():
    """Whitespace-only SQL must return INVALID_MODEL_OUTPUT safely."""
    text_to_sql = MagicMock()
    text_to_sql.build_context.return_value = "context"
    mock_gen = MagicMock()
    mock_gen.text = json.dumps({
        "status": "success",
        "sql": "   \n\t  ",
        "is_read_only": True
    })
    text_to_sql.run.return_value = mock_gen

    self_corr = MagicMock()
    pipeline = CopilotRuntimePipeline(text_to_sql, self_corr)

    resp = pipeline.run(CopilotAskRequest(question="Show accounts", conversation=()))
    assert resp.status == "Failed"
    assert resp.error_code == "INVALID_MODEL_OUTPUT"
    self_corr.run.assert_not_called()


def test_adversarial_typed_response_malformed_json():
    """Malformed non-JSON output returns INVALID_MODEL_OUTPUT without raising."""
    text_to_sql = MagicMock()
    text_to_sql.build_context.return_value = "context"
    mock_gen = MagicMock()
    mock_gen.text = "I cannot generate SQL for this request. Please try again."
    text_to_sql.run.return_value = mock_gen

    self_corr = MagicMock()
    pipeline = CopilotRuntimePipeline(text_to_sql, self_corr)

    resp = pipeline.run(CopilotAskRequest(question="Show accounts", conversation=()))
    assert resp.status == "Failed"
    assert resp.error_code == "INVALID_MODEL_OUTPUT"
    self_corr.run.assert_not_called()


# ==============================================================================
# 6. MULTI-STATEMENT READ-ONLY & PIGGYBACK INJECTION DEFENSE AUDIT
# ==============================================================================

def test_adversarial_multi_statement_all_select_accepted():
    """Multiple valid SELECT queries in one batch must pass all validations."""
    syntax, schema, rel, rls, _, schema_repo = _create_harness()
    batch_sql = (
        "SELECT a.account_id, a.balance_usd FROM accounts AS a WHERE a.branch_id = @UserBranchId;\n"
        "SELECT c.customer_id, c.first_name FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id WHERE a.branch_id = @UserBranchId;\n"
        "SELECT b.branch_id, b.branch_name FROM branches AS b WHERE b.branch_id = @UserBranchId"
    )
    assert syntax.validate(batch_sql).is_valid
    assert schema.validate(batch_sql, schema=schema_repo.get_schema()).is_valid
    assert rls.validate(batch_sql, schema=schema_repo.get_schema(), enforce_presence=True).is_valid


@pytest.mark.parametrize(
    "piggybacked_statement",
    [
        "DROP TABLE accounts",
        "UPDATE accounts SET balance_usd = 0 WHERE account_id = 1",
        "DELETE FROM customers WHERE customer_id = 1",
        "INSERT INTO branches (branch_id, branch_name) VALUES (99, 'Hacked')",
        "TRUNCATE TABLE transactions",
        "ALTER TABLE accounts ADD COLUMN hacked INT",
        "MERGE accounts AS target USING accounts AS source ON target.account_id = source.account_id WHEN MATCHED THEN DELETE;",
        "EXEC sp_msforeachtable 'DROP TABLE ?'",
    ],
)
def test_adversarial_multi_statement_piggybacked_writes_rejected(piggybacked_statement: str):
    """Any non-SELECT statement in a multi-statement batch rejects the entire batch."""
    syntax, schema, rel, rls, _, _ = _create_harness()
    batch_sql = f"SELECT a.account_id FROM accounts AS a WHERE a.branch_id = @UserBranchId;\n{piggybacked_statement}"
    result = syntax.validate(batch_sql)
    assert not result.is_valid, f"Failed to reject dangerous piggybacked SQL: {piggybacked_statement}"
    assert result.issues[0].type in ("NOT_READ_ONLY", "SYNTAX_ERROR")


def test_adversarial_multi_statement_second_stmt_missing_rls_rejected():
    """If Statement 1 passes RLS but Statement 2 accesses accounts without @UserBranchId, reject batch."""
    syntax, schema, rel, rls, _, schema_repo = _create_harness()
    batch_sql = (
        "SELECT a.account_id FROM accounts AS a WHERE a.branch_id = @UserBranchId;\n"
        "SELECT a.account_id, a.balance_usd FROM accounts AS a"
    )
    # Statement 1 is valid, Statement 2 is missing @UserBranchId
    res = rls.validate(batch_sql, schema=schema_repo.get_schema(), enforce_presence=True)
    assert not res.is_valid, "Batch with missing RLS in second statement must be rejected!"
    assert any("RLS" in i.type for i in res.issues)


# ==============================================================================
# 7. OBSERVABILITY, TRACE STABILITY & LATENCY AUDIT
# ==============================================================================

def test_adversarial_flow_tracing_skipped_stage_truthfulness():
    """When query passes initial deterministic validation, critic/correction must be truthfully marked skipped."""
    syntax, schema, rel, rls, repair, schema_repo = _create_harness()
    context = MagicMock()
    context.build_llm_context.return_value = "context"

    critic = MagicMock()
    critic.evaluate.return_value = CriticResult("PASS")

    correction = MagicMock()

    service = SelfCorrectionService(
        context_retrieval_service=context,
        syntax_validator=syntax,
        schema_validator=schema,
        relationship_validator=rel,
        critic_service=critic,
        finding_verifier=CriticFindingVerifier(schema_repo),
        correction_service=correction,
        max_attempts=3,
        rls_validator=rls,
        schema_provider=schema_repo,
        repair_service=repair,
    )

    sql = "SELECT a.account_id FROM accounts AS a WHERE a.branch_id = @UserBranchId"
    steps = []
    outcome = service.run("Show accounts", sql, trace_observer=steps.append, enforce_rls=True)

    assert outcome.is_valid
    assert outcome.attempts_used == 0
    correction.correct.assert_not_called()
    assert len(steps) == 1
    assert steps[0]["action"] == "passed"


def test_adversarial_critic_hallucinated_top_filter_discarded():
    """Critic claiming missing filter for top/highest branch when SQL already uses TOP and ORDER BY must be discarded."""
    _, _, _, _, _, schema_repo = _create_harness()
    verifier = CriticFindingVerifier(schema_repo)

    hallucinated_finding = CriticResult(
        status="FAIL",
        issues=(
            CriticIssue(
                type="MISSING_REQUESTED_FILTER",
                description="The query does not include a filter for the top branch based on the highest number of transactions.",
                evidence="",
            ),
        ),
    )

    sql = (
        "SELECT TOP 1 b.branch_name, b.manager_name, COUNT(t.transaction_id) AS transaction_count, "
        "SUM(t.amount_usd) AS total_amount "
        "FROM branches AS b "
        "INNER JOIN accounts AS a ON b.branch_id = a.branch_id "
        "INNER JOIN transactions AS t ON a.account_id = t.account_id "
        "GROUP BY b.branch_name, b.manager_name "
        "ORDER BY COUNT(t.transaction_id) DESC"
    )
    verified = verifier.verify(hallucinated_finding, schema=schema_repo.get_schema(), sql=sql)
    assert len(verified) == 0, f"Verifier failed to filter hallucinated top filter claim: {verified}"
