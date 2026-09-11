from unittest.mock import Mock

from src.application.dto.self_correction.critic_result import CriticResult
from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.application.dto.self_correction.validation_result import ValidationResult
from src.application.services.self_correction.self_correction_service import (
    SelfCorrectionService,
)


_SCHEMA = {
    "tables": {
        "customers": {"columns": [{"name": "customer_id"}]},
        "accounts": {"columns": [{"name": "customer_id"}, {"name": "branch_id"}]},
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


class _Context:
    def build_llm_context(self, question):
        return "context"


class _SchemaProvider:
    def get_schema(self):
        return _SCHEMA


class _SchemaValidator:
    def validate(self, sql, **kwargs):
        return ValidationResult.ok()

    def schema_slice(self, sql, **kwargs):
        return {"customers": _SCHEMA["tables"]["customers"]}

    def extract_tables(self, sql, **kwargs):
        return {"customers"}


class _SyntaxValidator:
    def validate(self, sql, **kwargs):
        return ValidationResult.ok()


class _Relationships:
    def validate(self, sql, **kwargs):
        return ValidationResult.ok()

    def relationships_for_tables(self, tables):
        return [
            {
                "from_table": "customers", "from_column": "customer_id",
                "to_table": "accounts", "to_column": "customer_id",
            }
        ] if {"customers", "accounts"}.issubset(tables) else []


class _Rls:
    def validate(self, sql, **kwargs):
        return ValidationResult.fail([
            ValidationIssue("RLS_PARAMETER_MISSING", "missing @UserBranchId", "rls")
        ])


def test_rls_correction_receives_required_account_schema_and_relationship():
    correction = Mock()
    correction.correct.return_value = None
    service = SelfCorrectionService(
        _Context(), _SyntaxValidator(), _SchemaValidator(), _Relationships(),
        Mock(), Mock(), correction, max_attempts=1,
        rls_validator=_Rls(), schema_provider=_SchemaProvider(),
    )

    service.run("show customers", "SELECT c.customer_id FROM customers c", enforce_rls=True)

    kwargs = correction.correct.call_args.kwargs
    assert "accounts" in kwargs["relevant_schema"]
    assert kwargs["relevant_relationships"]
