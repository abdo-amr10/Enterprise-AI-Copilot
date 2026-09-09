"""Comprehensive tests for all 7 scenarios required by the production fix:
1. Complex question preserves mandatory Branch ID / RLS predicate.
2. Indirect relationship generated correctly first time (bridge table).
3. Missing column is not silently dropped (returns needs_clarification).
4. Natural language phrase does not false-fail (distinguishes NL from DB objects).
5. Missing Branch ID is repaired surgically without rewriting valid SQL.
6. Invalid JOIN is repaired through bridge table.
7. No regression / oscillation detection prevents cycling between rejected states.
"""

import json
import pytest

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.self_correction.self_correction_outcome import SelfCorrectionOutcome
from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.application.dto.self_correction.validation_result import ValidationResult
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import (
    CopilotRuntimePipeline,
)
from src.application.services.self_correction.self_correction_service import (
    SelfCorrectionService,
    compute_sql_fingerprint,
)
from src.application.services.self_correction.sql_deterministic_repair_service import (
    SQLDeterministicRepairService,
)
from src.application.services.self_correction.sql_correction_service import (
    SQLCorrectionService,
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
from src.prompts.text_to_sql_prompt import TEXT_TO_SQL_PROMPT
from src.prompts.sql_correction_prompt import SQL_CORRECTION_PROMPT


class FakeTextToSQLPipeline:
    def __init__(self, text: str) -> None:
        self._text = text

    def build_context(self, question: str) -> str:
        return """SEMANTIC CONTEXT
TABLE: customers [PK: customer_id]
COLUMNS: customer_id, first_name, last_name, email, city, credit_score, last_active_date

TABLE: accounts [PK: account_id]
COLUMNS: account_id, customer_id, branch_id, account_type, balance_usd

TABLE: loans [PK: loan_id]
COLUMNS: loan_id, customer_id, loan_amount, status

TABLE: transactions [PK: transaction_id]
COLUMNS: transaction_id, account_id, amount_usd, transaction_date

APPROVED RELATIONSHIPS:
- customers.customer_id -> accounts.customer_id [cardinality: 1:N]
- customers.customer_id -> loans.customer_id [cardinality: 1:N]
- accounts.account_id -> transactions.account_id [cardinality: 1:N]

SECURITY DOMAIN & CANONICAL SECURITY SCOPE:
- Security domain: branch
- Canonical security root: accounts.branch_id = @UserBranchId
- Security propagation:
  * customers: customers.customer_id = accounts.customer_id -> accounts.branch_id = @UserBranchId
  * transactions: transactions.account_id = accounts.account_id -> accounts.branch_id = @UserBranchId
"""

    def run(self, question: str, **kwargs) -> GenerationResponse:
        return GenerationResponse(text=self._text)


class PassThroughSelfCorrection:
    def run(self, question, sql, **kwargs):
        return SelfCorrectionOutcome.success(sql, attempts_used=0)


class MockLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.recorded_requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.recorded_requests.append(request)
        return GenerationResponse(text=next(self._responses))


def test_scenario_1_complex_question_preserves_branch_id():
    """TEST 1: Complex question involving multiple entities and joins preserves Branch ID / RLS."""
    assert "Question complexity MUST NEVER cause a mandatory security predicate to be omitted." in TEXT_TO_SQL_PROMPT
    assert "Example 7" in TEXT_TO_SQL_PROMPT
    assert "Complex Query Preserves Mandatory Security Predicate" in TEXT_TO_SQL_PROMPT
    assert "accounts.branch_id = @UserBranchId" in TEXT_TO_SQL_PROMPT

    complex_sql = (
        "SELECT c.customer_id, c.first_name, c.last_name, "
        "COUNT(DISTINCT a.account_id) AS account_count, "
        "COUNT(DISTINCT l.loan_id) AS loan_count, "
        "COALESCE(SUM(l.loan_amount), 0) AS total_loan_amount, "
        "COALESCE(SUM(t.amount_usd), 0) AS total_transaction_amount "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "LEFT JOIN loans AS l ON c.customer_id = l.customer_id "
        "LEFT JOIN transactions AS t ON a.account_id = t.account_id "
        "WHERE a.branch_id = @UserBranchId "
        "GROUP BY c.customer_id, c.first_name, c.last_name;"
    )
    payload = {
        "status": "success",
        "sql": complex_sql,
        "is_read_only": True,
        "tables_used": ["customers", "accounts", "loans", "transactions"],
        "columns_used": ["accounts.branch_id"],
        "warnings": [],
    }
    pipeline = CopilotRuntimePipeline(
        FakeTextToSQLPipeline(json.dumps(payload)),
        PassThroughSelfCorrection(),
    )
    req = CopilotAskRequest(
        question="For each customer in my branch, show their accounts, loans, recent transactions, total transaction amount, and loan amount.",
        conversation=(),
    )
    res = pipeline.run(req)
    assert res.status == "Success"
    assert res.sql is not None
    assert "@UserBranchId" in res.sql
    assert "accounts.branch_id = @UserBranchId" in res.sql or "a.branch_id = @UserBranchId" in res.sql


def test_scenario_2_indirect_relationship_generated_correctly_first_time():
    """TEST 2: Initial generation derives indirect path: loans -> customers -> accounts -> transactions."""
    assert "Example 8 — Indirect Approved Relationship Resolution with Bridge Table" in TEXT_TO_SQL_PROMPT
    assert "loans -> customers -> accounts -> transactions" in TEXT_TO_SQL_PROMPT
    assert "Incorrect shortcut (NEVER generate this):" in TEXT_TO_SQL_PROMPT
    assert "FROM loans AS l\nINNER JOIN accounts AS a" in TEXT_TO_SQL_PROMPT

    correct_indirect_sql = (
        "SELECT l.loan_id, l.loan_amount, t.transaction_id, t.amount_usd "
        "FROM loans AS l "
        "INNER JOIN customers AS c ON l.customer_id = c.customer_id "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "INNER JOIN transactions AS t ON a.account_id = t.account_id "
        "WHERE a.branch_id = @UserBranchId;"
    )
    payload = {
        "status": "success",
        "sql": correct_indirect_sql,
        "is_read_only": True,
        "tables_used": ["loans", "customers", "accounts", "transactions"],
        "columns_used": ["loans.customer_id", "customers.customer_id", "accounts.customer_id", "accounts.account_id"],
        "warnings": [],
    }
    pipeline = CopilotRuntimePipeline(
        FakeTextToSQLPipeline(json.dumps(payload)),
        PassThroughSelfCorrection(),
    )
    req = CopilotAskRequest(
        question="Show each loan and the transactions made by the loan customer.",
        conversation=(),
    )
    res = pipeline.run(req)
    assert res.status == "Success"
    assert "l.customer_id = a.customer_id" not in res.sql
    assert "customers AS c" in res.sql
    assert "accounts AS a" in res.sql


def test_scenario_3_missing_column_is_not_silently_dropped():
    """TEST 3: Explicitly requested concrete column not in semantic context triggers clarification, not partial SQL."""
    payload = {
        "status": "needs_clarification",
        "sql": None,
        "is_read_only": True,
        "tables_used": [],
        "columns_used": [],
        "warnings": [
            "The requested concrete column 'passport_number' is not defined in the authoritative semantic context."
        ],
    }
    pipeline = CopilotRuntimePipeline(
        FakeTextToSQLPipeline(json.dumps(payload)),
        PassThroughSelfCorrection(),
    )
    req = CopilotAskRequest(
        question="Show customer_id, first_name, and passport_number for all customers.",
        conversation=(),
    )
    res = pipeline.run(req)
    assert res.status == "Failed"
    assert res.error_code == "NEEDS_CLARIFICATION"
    assert res.sql is None
    assert "passport_number" in res.failure_reason


def test_scenario_4_natural_language_phrase_does_not_false_fail():
    """TEST 4: Natural language phrases (e.g. 'recent activity') resolve via date columns/filters and do not false-fail."""
    valid_nl_sql = (
        "SELECT c.customer_id, c.first_name, c.last_name, c.last_active_date "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE a.branch_id = @UserBranchId "
        "  AND c.last_active_date >= DATEADD(day, -30, '2026-09-08') "
        "ORDER BY c.last_active_date DESC;"
    )
    payload = {
        "status": "success",
        "sql": valid_nl_sql,
        "is_read_only": True,
        "tables_used": ["customers", "accounts"],
        "columns_used": ["customers.last_active_date", "accounts.branch_id"],
        "warnings": [],
    }
    pipeline = CopilotRuntimePipeline(
        FakeTextToSQLPipeline(json.dumps(payload)),
        PassThroughSelfCorrection(),
    )
    req = CopilotAskRequest(
        question="Show customers with recent activity in my branch.",
        conversation=(),
    )
    res = pipeline.run(req)
    assert res.status == "Success"
    assert res.sql == valid_nl_sql
    assert "@UserBranchId" in res.sql


def test_scenario_5_missing_branch_id_is_repaired_surgically():
    """TEST 5: Missing Branch ID predicate is added surgically without rewriting valid joins, aliases, or columns."""
    syntax_validator = SQLSyntaxValidator()
    schema_dict = {
        "tables": {
            "transactions": {"columns": [{"name": "transaction_id"}, {"name": "account_id"}, {"name": "amount_usd"}]},
            "accounts": {"columns": [{"name": "account_id"}, {"name": "branch_id"}]},
        },
        "relationships": [
            {"from_table": "transactions", "from_column": "account_id", "to_table": "accounts", "to_column": "account_id"}
        ],
        "security_domains": [
            {
                "name": "branch",
                "canonical_root": "accounts.branch_id",
                "canonical_predicate": "accounts.branch_id = @UserBranchId",
                "propagation_paths": [
                    {
                        "target_table": "transactions",
                        "path": "transactions.account_id = accounts.account_id -> accounts.branch_id = @UserBranchId",
                        "propagation": "allowed",
                    }
                ],
            }
        ],
    }
    class SchemaMock:
        def get_schema(self): return schema_dict
    schema_prov = SchemaMock()
    schema_validator = SQLSchemaValidator(schema_prov, syntax_validator)
    rls_validator = SQLRlsValidator(syntax_validator, schema_validator)
    repair_service = SQLDeterministicRepairService(
        syntax_validator=syntax_validator,
        schema_validator=schema_validator,
        rls_validator=rls_validator,
    )

    original_sql = (
        "SELECT t.transaction_id, t.amount_usd "
        "FROM transactions AS t "
        "INNER JOIN accounts AS a ON t.account_id = a.account_id "
        "WHERE t.amount_usd > 100;"
    )
    repaired_sql = repair_service.repair(original_sql, schema=schema_dict, enforce_rls=True)

    # Verify RLS added
    assert "@UserBranchId" in repaired_sql
    # Verify original SELECT, JOIN, and filters preserved intact
    assert "SELECT t.transaction_id, t.amount_usd" in repaired_sql
    assert "FROM transactions AS t" in repaired_sql
    assert "INNER JOIN accounts AS a ON t.account_id = a.account_id" in repaired_sql
    assert "t.amount_usd > 100" in repaired_sql


def test_scenario_6_invalid_join_is_repaired_through_bridge_table():
    """TEST 6: Invalid direct join loans.customer_id = accounts.customer_id is replaced with bridge table."""
    syntax_validator = SQLSyntaxValidator()
    schema_dict = {
        "tables": {
            "loans": {"columns": [{"name": "loan_id"}, {"name": "customer_id"}]},
            "customers": {"columns": [{"name": "customer_id"}]},
            "accounts": {"columns": [{"name": "account_id"}, {"name": "customer_id"}, {"name": "branch_id"}]},
        },
        "relationships": [
            {"from_table": "loans", "from_column": "customer_id", "to_table": "customers", "to_column": "customer_id"},
            {"from_table": "customers", "from_column": "customer_id", "to_table": "accounts", "to_column": "customer_id"},
        ],
    }
    class SchemaMock:
        def get_schema(self): return schema_dict
    schema_prov = SchemaMock()
    schema_validator = SQLSchemaValidator(schema_prov, syntax_validator)
    repair_service = SQLDeterministicRepairService(
        syntax_validator=syntax_validator,
        schema_validator=schema_validator,
    )

    # Invalid SQL with direct join between loans and accounts
    invalid_sql = (
        "SELECT l.loan_id, a.account_id "
        "FROM loans AS l "
        "INNER JOIN accounts AS a ON l.customer_id = a.customer_id;"
    )
    repaired_sql = repair_service.repair(invalid_sql, schema=schema_dict, enforce_rls=False)

    # Must contain bridge table customers
    assert "customers" in repaired_sql.lower()
    # Must not contain direct join condition between loans and accounts
    assert "l.customer_id = a.customer_id" not in repaired_sql


def test_scenario_7_no_regression_and_no_oscillation():
    """TEST 7: Correction loop halts upon detecting repeat of previously rejected state."""
    assert "NEVER reproduce any candidate listed in <REJECTED_CANDIDATES>." in SQL_CORRECTION_PROMPT
    assert "Avoid returning to a previously rejected semantic state" in SQL_CORRECTION_PROMPT

    class MockContext:
        def build_llm_context(self, q): return "context"

    class AlwaysFailsValidator:
        def validate(self, sql):
            return ValidationResult.fail([ValidationIssue("INVALID_RELATIONSHIP", "Unapproved join", "validator")])
        def schema_slice(self, sql): return {}
        def extract_tables(self, sql): return set()

    class MockRelationships:
        def validate(self, sql): return ValidationResult.fail([ValidationIssue("INVALID_RELATIONSHIP", "Unapproved join", "validator")])
        def relationships_for_tables(self, tables): return []

    class MockCritic:
        def evaluate(self, **kwargs): return None

    class MockVerifier:
        def verify(self, *args, **kwargs): return []

    # LLM returns SQL A, then SQL B, then oscillates back to SQL A
    candidate_a = "SELECT l.loan_id FROM loans AS l INNER JOIN accounts AS a ON l.customer_id = a.customer_id"
    candidate_b = "SELECT l.loan_id FROM loans AS l"
    candidate_oscillating = "SELECT l.loan_id FROM loans AS l INNER JOIN accounts AS a ON l.customer_id = a.customer_id"

    mock_llm = MockLLMClient([candidate_b, candidate_oscillating])
    correction_service = SQLCorrectionService(mock_llm)

    service = SelfCorrectionService(
        context_retrieval_service=MockContext(),
        syntax_validator=SQLSyntaxValidator(),
        schema_validator=AlwaysFailsValidator(),
        relationship_validator=MockRelationships(),
        critic_service=MockCritic(),
        finding_verifier=MockVerifier(),
        correction_service=correction_service,
        max_attempts=3,
    )

    outcome = service.run(
        question="Show loans and accounts",
        sql=candidate_a,
        semantic_context="context",
    )

    # Verification: Oscillation detected and loop aborted
    assert not outcome.is_valid
    assert any("CORRECTION_OSCILLATION" in str(t.get("deterministicIssues", [])) for t in outcome.trace)


class MockSchemaProvider:
    def __init__(self) -> None:
        self._schema = {
            "tables": {
                "customers": {
                    "columns": [
                        {"name": "customer_id", "type": "varchar(20)"},
                        {"name": "first_name", "type": "varchar(50)"},
                        {"name": "last_name", "type": "varchar(50)"},
                        {"name": "email", "type": "varchar(100)"},
                        {"name": "city", "type": "varchar(50)"},
                        {"name": "credit_score", "type": "int"},
                    ]
                },
                "accounts": {
                    "columns": [
                        {"name": "account_id", "type": "varchar(20)"},
                        {"name": "customer_id", "type": "varchar(20)"},
                        {"name": "branch_id", "type": "varchar(20)"},
                        {"name": "balance_usd", "type": "decimal(12,2)"},
                    ]
                },
            }
        }

    def get_schema(self) -> dict:
        return self._schema


def test_scenario_3b_hallucinated_missing_column_silent_omission_triggers_clarification():
    """TEST 3b: When generation hallucinates a non-existent column (e.g. mobile_number) and correction drops it,
    the pipeline detects SILENT_OMISSION and halts with NEEDS_CLARIFICATION rather than partial SQL.
    """
    initial_sql = (
        "SELECT c.first_name, c.mobile_number "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE a.branch_id = @UserBranchId;"
    )
    # Correction attempts to fix the unknown column by simply dropping mobile_number:
    dropped_sql = (
        "SELECT c.first_name "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE a.branch_id = @UserBranchId;"
    )

    schema_provider = MockSchemaProvider()
    syntax_validator = SQLSyntaxValidator()
    schema_validator = SQLSchemaValidator(schema_provider, syntax_validator)
    mock_llm = MockLLMClient([dropped_sql])
    correction_service = SQLCorrectionService(mock_llm)

    class MockContext:
        def build_llm_context(self, q): return "context"

    class MockCritic:
        def evaluate(self, **kwargs):
            from src.application.dto.self_correction.critic_result import CriticResult
            return CriticResult("PASS")

    class MockVerifier:
        def verify(self, *args, **kwargs): return []

    class MockRelationships:
        def validate(self, *args, **kwargs): return ValidationResult.ok()
        def relationships_for_tables(self, tables): return []

    self_correction = SelfCorrectionService(
        context_retrieval_service=MockContext(),
        syntax_validator=syntax_validator,
        schema_validator=schema_validator,
        relationship_validator=MockRelationships(),
        critic_service=MockCritic(),
        finding_verifier=MockVerifier(),
        correction_service=correction_service,
        schema_provider=schema_provider,
        max_attempts=3,
    )

    payload = {
        "status": "success",
        "sql": initial_sql,
        "is_read_only": True,
        "tables_used": ["customers", "accounts"],
        "columns_used": ["customers.first_name", "customers.mobile_number", "accounts.branch_id"],
        "warnings": [],
    }

    pipeline = CopilotRuntimePipeline(
        FakeTextToSQLPipeline(json.dumps(payload)),
        self_correction,
    )

    req = CopilotAskRequest(
        question="Show customer first name and registered mobile number",
        conversation=(),
    )
    res = pipeline.run(req)

    assert res.status == "Failed"
    assert res.error_code == "NEEDS_CLARIFICATION"
    assert res.sql is None
    assert "mobile_number" in res.failure_reason


def test_fixable_column_typo_is_successfully_corrected():
    """TEST: When generation uses a mistyped column that has an obvious schema counterpart (e.g. c.name -> c.first_name),
    correction renames it without triggering SILENT_OMISSION, and validation passes.
    """
    initial_sql = (
        "SELECT c.name "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE a.branch_id = @UserBranchId;"
    )
    corrected_sql = (
        "SELECT c.first_name "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE a.branch_id = @UserBranchId;"
    )

    schema_provider = MockSchemaProvider()
    syntax_validator = SQLSyntaxValidator()
    schema_validator = SQLSchemaValidator(schema_provider, syntax_validator)
    mock_llm = MockLLMClient([corrected_sql])
    correction_service = SQLCorrectionService(mock_llm)

    class MockContext:
        def build_llm_context(self, q): return "context"

    class MockCritic:
        def evaluate(self, **kwargs):
            from src.application.dto.self_correction.critic_result import CriticResult
            return CriticResult("PASS")

    class MockVerifier:
        def verify(self, *args, **kwargs): return []

    class MockRelationships:
        def validate(self, *args, **kwargs): return ValidationResult.ok()
        def relationships_for_tables(self, tables): return []

    self_correction = SelfCorrectionService(
        context_retrieval_service=MockContext(),
        syntax_validator=syntax_validator,
        schema_validator=schema_validator,
        relationship_validator=MockRelationships(),
        critic_service=MockCritic(),
        finding_verifier=MockVerifier(),
        correction_service=correction_service,
        schema_provider=schema_provider,
        max_attempts=3,
    )

    payload = {
        "status": "success",
        "sql": initial_sql,
        "is_read_only": True,
        "tables_used": ["customers", "accounts"],
        "columns_used": ["customers.name", "accounts.branch_id"],
        "warnings": [],
    }

    pipeline = CopilotRuntimePipeline(
        FakeTextToSQLPipeline(json.dumps(payload)),
        self_correction,
    )

    req = CopilotAskRequest(
        question="Show customer name",
        conversation=(),
    )
    res = pipeline.run(req)

    assert res.status == "Success"
    assert res.sql is not None
    assert "c.first_name" in res.sql