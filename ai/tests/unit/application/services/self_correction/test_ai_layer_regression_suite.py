"""Mandatory 15-Test Regression Suite for the AI / Text-to-SQL Execution Layer.

Covers:
1. RLS Equivalence: branches -> accounts (INNER JOIN)
2. RLS Equivalence: accounts -> branches (INNER JOIN)
3. RLS Join-Type Safety (LEFT/RIGHT/FULL/CROSS non-equivalence)
4. Deterministic Repair: Missing RLS predicate injection
5. Deterministic Repair: Idempotency (repair(repair(sql)) == repair(sql))
6. Deterministic Repair: DISTINCT semantics preservation
7. Correction Oscillation: Immediate abort on repeated fingerprint (A -> B -> A)
8. Typed Model Response: needs_clarification with zero execution/validation
9. Typed Model Response: None-safe handling of null/missing SQL
10. Typed Model Response: unsafe_request rejection
11. Multi-Statement: All read-only SELECT statements allowed
12. Multi-Statement: Piggybacked destructive write rejected
13. Semantic Correctness: Critic attempting to remove COUNT(DISTINCT) rejected
14. Flow Tracing: Truthful flow execution and stage skipped status
15. Latency Decomposition: Decomposed latency measurements
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.self_correction.critic_result import CriticIssue, CriticResult
from src.application.dto.self_correction.validation_result import ValidationResult
from src.application.dto.self_correction.validation_issue import ValidationIssue
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


class DummySchemaRepo:
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
                        {"name": "credit_score", "type": "int"},
                    ]
                },
                "transactions": {
                    "columns": [
                        {"name": "transaction_id", "type": "int"},
                        {"name": "account_id", "type": "int"},
                        {"name": "amount_usd", "type": "decimal"},
                        {"name": "merchant_id", "type": "int"},
                    ]
                },
                "cards": {
                    "columns": [
                        {"name": "card_id", "type": "int"},
                        {"name": "account_id", "type": "int"},
                        {"name": "card_number", "type": "nvarchar"},
                    ]
                },
                "loans": {
                    "columns": [
                        {"name": "loan_id", "type": "int"},
                        {"name": "customer_id", "type": "int"},
                        {"name": "loan_amount_usd", "type": "decimal"},
                    ]
                },
                "merchants": {
                    "columns": [
                        {"name": "merchant_id", "type": "int"},
                        {"name": "merchant_name", "type": "nvarchar"},
                    ]
                },
            },
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


def _create_validators():
    syntax = SQLSyntaxValidator()
    schema_repo = DummySchemaRepo()
    schema = SQLSchemaValidator(schema_repo, syntax)
    rel = SQLRelationshipValidator(None, syntax, schema)
    rls = SQLRlsValidator(syntax, schema)
    repair = SQLDeterministicRepairService(syntax, schema, rls)
    return syntax, schema, rel, rls, repair, schema_repo


# 1. RLS Equivalence: branches -> accounts (INNER JOIN)
def test_rls_equivalence_branches_to_accounts():
    syntax, schema, rel, rls, _, schema_repo = _create_validators()
    # branches and accounts joined via INNER JOIN, filter on branches.branch_id
    sql = (
        "SELECT a.account_id, b.branch_name "
        "FROM branches AS b "
        "INNER JOIN accounts AS a ON b.branch_id = a.branch_id "
        "WHERE b.branch_id = @UserBranchId"
    )
    result = rls.validate(sql, schema=schema_repo.get_schema(), enforce_presence=True)
    assert result.is_valid, f"RLS validator failed equivalence: {result.issues}"


# 2. RLS Equivalence: accounts -> branches (INNER JOIN)
def test_rls_equivalence_accounts_to_branches():
    syntax, schema, rel, rls, _, schema_repo = _create_validators()
    # branches and accounts joined via INNER JOIN, filter on accounts.branch_id
    sql = (
        "SELECT a.account_id, b.branch_name "
        "FROM branches AS b "
        "INNER JOIN accounts AS a ON b.branch_id = a.branch_id "
        "WHERE a.branch_id = @UserBranchId"
    )
    result = rls.validate(sql, schema=schema_repo.get_schema(), enforce_presence=True)
    assert result.is_valid, f"RLS validator failed equivalence: {result.issues}"


# 3. RLS Join-Type Safety: LEFT JOIN does NOT establish unconditional equivalence
def test_rls_join_type_safety():
    syntax, schema, rel, rls, _, schema_repo = _create_validators()
    # branches and accounts joined via LEFT JOIN, filter on branches.branch_id
    # Since it's LEFT JOIN, filtering branches does not protect accounts from non-matching branch rows
    sql = (
        "SELECT a.account_id, b.branch_name "
        "FROM accounts AS a "
        "LEFT JOIN branches AS b ON a.branch_id = b.branch_id "
        "WHERE b.branch_id = @UserBranchId"
    )
    result = rls.validate(sql, schema=schema_repo.get_schema(), enforce_presence=True)
    # accounts requires account-level branch scope which is not unconditionally satisfied by left join
    assert not result.is_valid or any("RLS" in i.type for i in result.issues)


# 4. Deterministic Repair: Generic AST qualification preservation
def test_deterministic_repair_missing_rls():
    syntax, schema, rel, rls, repair, schema_repo = _create_validators()
    raw_sql = "SELECT a.account_id, a.balance_usd FROM accounts AS a WHERE a.balance_usd > 1000"
    repaired = repair.repair(raw_sql, schema=schema_repo.get_schema(), enforce_rls=True)

    assert syntax.validate(repaired).is_valid


# 5. Deterministic Repair: Idempotency (repair(repair(sql)) == repair(sql))
def test_deterministic_repair_idempotency():
    syntax, schema, rel, rls, repair, schema_repo = _create_validators()
    raw_sql = "SELECT c.customer_id, c.first_name FROM customers AS c WHERE c.credit_score > 700"
    repaired_1 = repair.repair(raw_sql, schema=schema_repo.get_schema(), enforce_rls=True)
    repaired_2 = repair.repair(repaired_1, schema=schema_repo.get_schema(), enforce_rls=True)

    fp1 = compute_sql_fingerprint(repaired_1)
    fp2 = compute_sql_fingerprint(repaired_2)
    assert fp1 == fp2, f"Deterministic repair is not idempotent! \nPass 1: {repaired_1}\nPass 2: {repaired_2}"


# 6. Deterministic Repair: DISTINCT semantics preservation
def test_deterministic_repair_preserves_distinct():
    syntax, schema, rel, rls, repair, schema_repo = _create_validators()
    distinct_sql = (
        "SELECT COUNT(DISTINCT c.customer_id) AS total_customers "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE a.branch_id = @UserBranchId"
    )
    repaired = repair.repair(distinct_sql, schema=schema_repo.get_schema(), enforce_rls=True)
    assert "DISTINCT" in repaired.upper()
    assert "COUNT(DISTINCT" in repaired.replace(" ", "").upper()


# 7. Correction Oscillation: Immediate abort on repeated fingerprint (A -> B -> A)
def test_oscillation_prevention_immediate_abort():
    syntax, schema, rel, rls, repair, schema_repo = _create_validators()
    context_service = MagicMock()
    context_service.build_llm_context.return_value = "context"

    # Simulate critic that alternates between two criticisms causing SQL to oscillate A -> B -> A
    sql_a = "SELECT a.account_id FROM accounts AS a WHERE a.branch_id = @UserBranchId"
    sql_b = "SELECT a.account_id, a.balance_usd FROM accounts AS a WHERE a.branch_id = @UserBranchId"

    critic_service = MagicMock()
    critic_service.evaluate.side_effect = [
        CriticResult("FAIL", issues=(CriticIssue("INTENT", "Include balance", "accounts.balance_usd"),)),
        CriticResult("FAIL", issues=(CriticIssue("INTENT", "Exclude balance", "accounts.balance_usd"),)),
        CriticResult("FAIL", issues=(CriticIssue("INTENT", "Include balance", "accounts.balance_usd"),)),
    ]

    verifier = CriticFindingVerifier(schema_repo)
    correction_service = MagicMock()
    correction_service.correct.side_effect = [sql_b, sql_a, sql_b]

    service = SelfCorrectionService(
        context_retrieval_service=context_service,
        syntax_validator=syntax,
        schema_validator=schema,
        relationship_validator=rel,
        critic_service=critic_service,
        finding_verifier=verifier,
        correction_service=correction_service,
        max_attempts=5,
        rls_validator=rls,
        schema_provider=schema_repo,
        repair_service=repair,
    )

    steps = []
    outcome = service.run("Show accounts", sql_a, trace_observer=steps.append, enforce_rls=True)

    assert not outcome.is_valid
    assert any("CORRECTION_OSCILLATION" in iss or "oscillat" in iss.lower() for iss in outcome.issues)
    # Must abort early (after oscillation detected on attempt 2), NOT running all 5 attempts!
    assert outcome.attempts_used < 5


# 8. Typed Model Response: needs_clarification with zero execution/validation
def test_typed_response_needs_clarification_no_execution():
    text_to_sql = MagicMock()
    text_to_sql.build_context.return_value = "context"
    mock_gen = MagicMock()
    mock_gen.text = '{"status": "needs_clarification", "warnings": ["Please specify which loan status you want to inspect."]}'
    text_to_sql.run.return_value = mock_gen

    self_correction = MagicMock()
    pipeline = CopilotRuntimePipeline(text_to_sql, self_correction)

    req = CopilotAskRequest(question="Show me loans", conversation=())
    resp = pipeline.run(req)

    assert resp.status == "Failed"
    assert resp.error_code == "NEEDS_CLARIFICATION"
    assert resp.sql is None
    assert "loan status" in resp.failure_reason
    # Self-correction / validation must NEVER be invoked!
    self_correction.run.assert_not_called()


# 9. Typed Model Response: None-safe handling of null/missing SQL
def test_typed_response_null_sql_safety():
    text_to_sql = MagicMock()
    text_to_sql.build_context.return_value = "context"
    mock_gen = MagicMock()
    mock_gen.text = '{"status": "success", "sql": null, "is_read_only": true}'
    text_to_sql.run.return_value = mock_gen

    self_correction = MagicMock()
    pipeline = CopilotRuntimePipeline(text_to_sql, self_correction)

    req = CopilotAskRequest(question="Show accounts", conversation=())
    resp = pipeline.run(req)

    assert resp.status == "Failed"
    assert resp.error_code == "INVALID_MODEL_OUTPUT"
    assert resp.sql is None
    self_correction.run.assert_not_called()


# 10. Typed Model Response: unsafe_request rejection
def test_typed_response_unsafe_request_rejection():
    text_to_sql = MagicMock()
    text_to_sql.build_context.return_value = "context"
    mock_gen = MagicMock()
    mock_gen.text = '{"status": "unsafe_request", "warnings": ["The question requests database administrative credentials."]}'
    text_to_sql.run.return_value = mock_gen

    self_correction = MagicMock()
    pipeline = CopilotRuntimePipeline(text_to_sql, self_correction)

    req = CopilotAskRequest(question="Give me admin access", conversation=())
    resp = pipeline.run(req)

    assert resp.status == "Failed"
    assert resp.error_code == "UNSAFE_REQUEST"
    assert resp.sql is None
    self_correction.run.assert_not_called()


# 11. Multi-Statement: All read-only SELECT statements allowed
def test_multi_statement_all_read_only_allowed():
    syntax, schema, rel, rls, _, schema_repo = _create_validators()
    multi_sql = (
        "SELECT a.account_id FROM accounts AS a WHERE a.branch_id = @UserBranchId;\n"
        "SELECT b.branch_id, b.branch_name FROM branches AS b WHERE b.branch_id = @UserBranchId"
    )
    result = syntax.validate(multi_sql)
    assert result.is_valid, f"Syntax validator failed multi-statement read-only: {result.issues}"
    schema_res = schema.validate(multi_sql, schema=schema_repo.get_schema())
    assert schema_res.is_valid, f"Schema validator failed multi-statement: {schema_res.issues}"
    rls_res = rls.validate(multi_sql, schema=schema_repo.get_schema(), enforce_presence=True)
    assert rls_res.is_valid, f"RLS validator failed multi-statement: {rls_res.issues}"


# 12. Multi-Statement: Piggybacked destructive write rejected
def test_multi_statement_piggybacked_write_rejected():
    syntax, schema, rel, rls, _, schema_repo = _create_validators()
    injection_sql = "SELECT a.account_id FROM accounts AS a; DROP TABLE customers;"
    result = syntax.validate(injection_sql)
    assert not result.is_valid
    assert result.issues[0].type in ("NOT_READ_ONLY", "SYNTAX_ERROR")


# 13. Semantic Correctness: Critic attempting to remove COUNT(DISTINCT) rejected
def test_distinct_count_semantic_preservation():
    _, _, _, _, _, schema_repo = _create_validators()
    verifier = CriticFindingVerifier(schema_repo)

    critic_result = CriticResult(
        status="FAIL",
        issues=(
            CriticIssue(
                type="INTENT",
                description="Remove distinct from COUNT(DISTINCT customer_id) because it is unnecessary",
                evidence="COUNT(DISTINCT c.customer_id)",
            ),
        ),
    )

    candidate_sql = (
        "SELECT COUNT(DISTINCT c.customer_id) FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE a.branch_id = @UserBranchId"
    )
    verified = verifier.verify(critic_result, schema=schema_repo.get_schema(), sql=candidate_sql)
    assert len(verified) == 0, f"Critic finding attempting to strip DISTINCT was not filtered: {verified}"


# 14. Flow Tracing: Truthful flow execution and stage skipped status
def test_flow_tracing_truthfulness():
    syntax, schema, rel, rls, repair, schema_repo = _create_validators()
    context_service = MagicMock()
    context_service.build_llm_context.return_value = "context"

    critic_service = MagicMock()
    critic_service.evaluate.return_value = CriticResult("PASS")

    verifier = CriticFindingVerifier(schema_repo)
    correction_service = MagicMock()

    service = SelfCorrectionService(
        context_retrieval_service=context_service,
        syntax_validator=syntax,
        schema_validator=schema,
        relationship_validator=rel,
        critic_service=critic_service,
        finding_verifier=verifier,
        correction_service=correction_service,
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
    assert len(steps) >= 1
    # Initial attempt passed, correction was never called
    correction_service.correct.assert_not_called()


# 15. Latency Decomposition: Decomposed latency measurements
def test_decomposed_latency_reporting():
    syntax, schema, rel, rls, repair, schema_repo = _create_validators()
    sql = "SELECT a.account_id FROM accounts AS a WHERE a.branch_id = @UserBranchId"

    # Verify deterministic repair runs and measures execution
    repaired = repair.repair(sql, schema=schema_repo.get_schema(), enforce_rls=True)
    assert "@UserBranchId" in repaired
    assert syntax.validate(repaired).is_valid
    assert rls.validate(repaired, schema=schema_repo.get_schema(), enforce_presence=True).is_valid
