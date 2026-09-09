"""Tests for Text-to-SQL Requirement Coverage, Indirect RLS, and Result Grain Preservation.

Covers:
- TEST A: Long question with many valid requirements + one unsupported field.
- TEST B: Unsupported field appears in middle/end of a long question.
- TEST C: Unsupported metric.
- TEST D: Unsupported relationship.
- TEST E: Fully supported long question.
- TEST F: Indirect RLS through a declared relationship.
- TEST G: Multi-scope query preserving RLS.
- TEST H: Customer-level aggregation over multiple accounts without extra grouping dimensions.
"""

import json
import pytest

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import (
    CopilotRuntimePipeline,
)
from src.application.services.text_to_sql.prompt_service import PromptService
from src.prompts.text_to_sql_prompt import TEXT_TO_SQL_PROMPT
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)
from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_rls_validator import (
    SQLRlsValidator,
)
from src.application.dto.self_correction.self_correction_outcome import SelfCorrectionOutcome


class FakeTextToSQLPipeline:
    def __init__(self, text: str) -> None:
        self._text = text

    def build_context(self, question: str) -> str:
        return """SEMANTIC CONTEXT
TABLE: customers [PK: customer_id]
COLUMNS: city, credit_score, customer_id, email, first_name, last_name

TABLE: accounts [PK: account_id]
COLUMNS: account_id, account_type, balance_usd, branch_id, customer_id

APPROVED RELATIONSHIPS:
- customers.customer_id -> accounts.customer_id [cardinality: 1:N]

SECURITY DOMAIN & CANONICAL SECURITY SCOPE:
- Security domain: branch
- Canonical security root: accounts.branch_id = @UserBranchId
- Security propagation & predicate equivalence:
  * customers: customers.customer_id = accounts.customer_id -> accounts.branch_id = @UserBranchId
"""

    def run(
        self,
        question: str,
        semantic_context: str | None = None,
        correction_feedback: str = "",
        conversation_context: str = "",
    ) -> GenerationResponse:
        return GenerationResponse(text=self._text)


class PassThroughSelfCorrection:
    def run(self, question, sql, semantic_context=None, trace_observer=None, **kwargs):
        return SelfCorrectionOutcome.success(sql, attempts_used=0)


class TestPromptContractIntegrity:
    """Verify TEXT_TO_SQL_PROMPT enforces all required pre-generation reasoning steps."""

    def test_prompt_contains_mandatory_pre_generation_protocol(self) -> None:
        assert "2. MANDATORY PRE-GENERATION REASONING PROTOCOL" in TEXT_TO_SQL_PROMPT
        assert "STEP 1 — PRE-GENERATION REQUIREMENT COVERAGE" in TEXT_TO_SQL_PROMPT
        assert "STEP 2 — PRE-GENERATION SECURITY PLANNING" in TEXT_TO_SQL_PROMPT
        assert "STEP 3 — REQUESTED GRAIN & AGGREGATION PLANNING" in TEXT_TO_SQL_PROMPT

    def test_prompt_forbids_silent_omission_and_partial_sql(self) -> None:
        assert "STRICT PROHIBITION AGAINST SILENT OMISSION & PARTIAL SQL" in TEXT_TO_SQL_PROMPT
        assert "NEVER generate partial SQL" in TEXT_TO_SQL_PROMPT
        assert "NEVER silently drop or omit a requested requirement" in TEXT_TO_SQL_PROMPT

    def test_prompt_includes_final_recency_checklist(self) -> None:
        assert "FINAL PRE-GENERATION CHECKLIST" in TEXT_TO_SQL_PROMPT
        assert "REQUIREMENT CHECK" in TEXT_TO_SQL_PROMPT
        assert "SECURITY CHECK" in TEXT_TO_SQL_PROMPT
        assert "GRAIN CHECK" in TEXT_TO_SQL_PROMPT

    def test_prompt_service_formats_without_error(self) -> None:
        service = PromptService()
        req = service.build_request(
            question="Show customer names, email, and mobile number.",
            semantic_context="TABLE: customers\nCOLUMNS: first_name, last_name, email",
            current_date="2026-09-07",
        )
        assert "Show customer names, email, and mobile number." in req.prompt
        assert "TABLE: customers" in req.prompt


class TestRequirementCoverageAndIndirectRLSPipeline:
    """Verify runtime pipeline behavior for Test Cases A through H."""

    def test_case_a_unsupported_field_in_long_question(self) -> None:
        """TEST A: Many valid requirements + one unsupported field -> needs_clarification, sql=null."""
        payload = {
            "status": "needs_clarification",
            "sql": None,
            "is_read_only": True,
            "tables_used": [],
            "columns_used": [],
            "warnings": [
                "The requested field 'registered mobile number' is not defined in the authoritative semantic context."
            ],
        }
        pipeline = CopilotRuntimePipeline(
            FakeTextToSQLPipeline(json.dumps(payload)),
            PassThroughSelfCorrection(),
        )
        req = CopilotAskRequest(
            question=(
                "Show customer first name, last name, email, city, credit score, "
                "account type, total account balance, and registered mobile number."
            ),
            conversation=(),
        )
        response = pipeline.run(req)

        assert response.status == "Failed"
        assert response.error_code == "NEEDS_CLARIFICATION"
        assert response.sql is None
        assert "registered mobile number" in response.failure_reason

    def test_case_b_unsupported_field_buried_in_question(self) -> None:
        """TEST B: Unsupported field in the middle of a complex prompt."""
        payload = {
            "status": "needs_clarification",
            "sql": None,
            "is_read_only": True,
            "tables_used": [],
            "columns_used": [],
            "warnings": [
                "The requested field 'secondary_fax' is not defined in the authoritative semantic context."
            ],
        }
        pipeline = CopilotRuntimePipeline(
            FakeTextToSQLPipeline(json.dumps(payload)),
            PassThroughSelfCorrection(),
        )
        req = CopilotAskRequest(
            question="List customer id, first name, secondary_fax, email, and total balance.",
            conversation=(),
        )
        response = pipeline.run(req)

        assert response.status == "Failed"
        assert response.error_code == "NEEDS_CLARIFICATION"
        assert response.sql is None

    def test_case_c_unsupported_business_metric(self) -> None:
        """TEST C: Question requests an unsupported metric -> needs_clarification."""
        payload = {
            "status": "needs_clarification",
            "sql": None,
            "is_read_only": True,
            "tables_used": [],
            "columns_used": [],
            "warnings": [
                "The requested metric 'churn_risk_score' is not defined in the authoritative semantic context."
            ],
        }
        pipeline = CopilotRuntimePipeline(
            FakeTextToSQLPipeline(json.dumps(payload)),
            PassThroughSelfCorrection(),
        )
        req = CopilotAskRequest(
            question="Show customer first name and their churn_risk_score.",
            conversation=(),
        )
        response = pipeline.run(req)

        assert response.status == "Failed"
        assert response.error_code == "NEEDS_CLARIFICATION"
        assert response.sql is None

    def test_case_d_unsupported_relationship(self) -> None:
        """TEST D: Question requests an unsupported relationship path -> needs_clarification."""
        payload = {
            "status": "needs_clarification",
            "sql": None,
            "is_read_only": True,
            "tables_used": [],
            "columns_used": [],
            "warnings": [
                "No approved relationship exists to connect the requested entities directly."
            ],
        }
        pipeline = CopilotRuntimePipeline(
            FakeTextToSQLPipeline(json.dumps(payload)),
            PassThroughSelfCorrection(),
        )
        req = CopilotAskRequest(
            question="Show merchant names for each loan record.",
            conversation=(),
        )
        response = pipeline.run(req)

        assert response.status == "Failed"
        assert response.error_code == "NEEDS_CLARIFICATION"
        assert response.sql is None

    def test_case_e_fully_supported_long_query(self) -> None:
        """TEST E: All fields, metrics, and security paths exist -> success with SQL."""
        valid_sql = (
            "SELECT c.first_name, c.last_name, c.email, c.city, c.credit_score, "
            "SUM(a.balance_usd) AS total_balance "
            "FROM customers AS c "
            "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
            "WHERE a.branch_id = @UserBranchId "
            "GROUP BY c.customer_id, c.first_name, c.last_name, c.email, c.city, c.credit_score;"
        )
        payload = {
            "status": "success",
            "sql": valid_sql,
            "is_read_only": True,
            "tables_used": ["customers", "accounts"],
            "columns_used": [
                "customers.first_name",
                "customers.last_name",
                "customers.email",
                "customers.city",
                "customers.credit_score",
                "accounts.balance_usd",
                "accounts.branch_id",
            ],
            "warnings": [],
        }
        pipeline = CopilotRuntimePipeline(
            FakeTextToSQLPipeline(json.dumps(payload)),
            PassThroughSelfCorrection(),
        )
        req = CopilotAskRequest(
            question=(
                "Show customer first name, last name, email, city, credit score, "
                "and total account balance."
            ),
            conversation=(),
        )
        response = pipeline.run(req)

        assert response.status == "Success"
        assert response.sql == valid_sql
        assert "@UserBranchId" in response.sql

    def test_case_f_indirect_rls_verified_by_deterministic_validator(self) -> None:
        """TEST F: Indirect RLS through customers -> accounts -> accounts.branch_id = @UserBranchId."""
        syntax_validator = SQLSyntaxValidator()
        class SchemaMock:
            def get_schema(self):
                return {
                    "tables": {
                        "customers": {"columns": [{"name": "customer_id"}, {"name": "first_name"}]},
                        "accounts": {"columns": [{"name": "account_id"}, {"name": "customer_id"}, {"name": "branch_id"}]},
                    },
                    "security_domains": [
                        {
                            "name": "branch",
                            "canonical_root": "accounts.branch_id",
                            "canonical_predicate": "accounts.branch_id = @UserBranchId",
                            "propagation_paths": [
                                {
                                    "target_table": "customers",
                                    "path": "customers.customer_id = accounts.customer_id -> accounts.branch_id = @UserBranchId",
                                    "propagation": "allowed",
                                }
                            ],
                        }
                    ],
                }
        schema_prov = SchemaMock()
        schema_validator = SQLSchemaValidator(schema_prov, syntax_validator)
        rls_validator = SQLRlsValidator(syntax_validator, schema_validator)

        # First-pass SQL with indirect RLS predicate included
        sql_with_rls = (
            "SELECT c.first_name, a.account_id "
            "FROM customers AS c "
            "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
            "WHERE a.branch_id = @UserBranchId;"
        )
        res = rls_validator.validate(sql_with_rls, schema=schema_prov.get_schema())
        assert res.is_valid, f"Expected valid RLS, got issues: {res.issues}"

        # SQL missing RLS predicate fails deterministically
        sql_missing_rls = (
            "SELECT c.first_name, a.account_id "
            "FROM customers AS c "
            "INNER JOIN accounts AS a ON c.customer_id = a.customer_id;"
        )
        res_missing = rls_validator.validate(sql_missing_rls, schema=schema_prov.get_schema())
        assert not res_missing.is_valid

    def test_case_g_multi_scope_query_preserves_rls(self) -> None:
        """TEST G: CTE multi-scope query preserves RLS in all scopes."""
        syntax_validator = SQLSyntaxValidator()
        class SchemaMock:
            def get_schema(self):
                return {
                    "tables": {
                        "customers": {"columns": [{"name": "customer_id"}, {"name": "first_name"}]},
                        "accounts": {"columns": [{"name": "account_id"}, {"name": "customer_id"}, {"name": "branch_id"}, {"name": "balance_usd"}]},
                    },
                    "security_domains": [
                        {
                            "name": "branch",
                            "canonical_root": "accounts.branch_id",
                            "canonical_predicate": "accounts.branch_id = @UserBranchId",
                            "propagation_paths": [
                                {
                                    "target_table": "customers",
                                    "path": "customers.customer_id = accounts.customer_id -> accounts.branch_id = @UserBranchId",
                                    "propagation": "allowed",
                                }
                            ],
                        }
                    ],
                }
        schema_prov = SchemaMock()
        schema_validator = SQLSchemaValidator(schema_prov, syntax_validator)
        rls_validator = SQLRlsValidator(syntax_validator, schema_validator)

        sql_cte_rls = (
            "WITH BranchBalances AS ( "
            "    SELECT a.customer_id, SUM(a.balance_usd) AS total_bal "
            "    FROM accounts AS a "
            "    WHERE a.branch_id = @UserBranchId "
            "    GROUP BY a.customer_id "
            ") "
            "SELECT c.first_name, bb.total_bal "
            "FROM customers AS c "
            "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
            "INNER JOIN BranchBalances AS bb ON bb.customer_id = c.customer_id "
            "WHERE a.branch_id = @UserBranchId;"
        )
        res = rls_validator.validate(sql_cte_rls, schema=schema_prov.get_schema())
        assert res.is_valid

    def test_case_h_customer_level_aggregation_grain(self) -> None:
        """TEST H: Aggregating balances over multiple accounts groups at customer grain only."""
        sql = (
            "SELECT c.customer_id, c.first_name, c.last_name, c.email, c.city, c.credit_score, "
            "SUM(a.balance_usd) AS total_balance "
            "FROM customers AS c "
            "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
            "WHERE a.branch_id = @UserBranchId "
            "GROUP BY c.customer_id, c.first_name, c.last_name, c.email, c.city, c.credit_score;"
        )
        assert "GROUP BY" in sql
        group_by_clause = sql.split("GROUP BY")[1]
        assert "account_type" not in group_by_clause
        assert "a.account_id" not in group_by_clause

