from src.application.services.self_correction.validators.sql_rls_validator import SQLRlsValidator
from src.application.services.self_correction.validators.sql_schema_validator import SQLSchemaValidator
from src.application.services.self_correction.validators.sql_syntax_validator import SQLSyntaxValidator


class _Schema:
    def get_schema(self):
        return {"tables": {name: {"columns": []} for name in (
            "branches", "accounts", "transactions", "cards", "customers", "loans", "merchants"
        )}}


def _validator():
    syntax = SQLSyntaxValidator()
    return SQLRlsValidator(syntax, SQLSchemaValidator(_Schema(), syntax))


def test_accepts_every_backend_rls_mapping():
    cases = [
        "SELECT b.branch_name FROM branches b WHERE b.branch_id = @UserBranchId",
        "SELECT a.account_id FROM accounts a WHERE a.branch_id = @UserBranchId",
        "SELECT t.transaction_id FROM transactions t INNER JOIN accounts a ON t.account_id = a.account_id WHERE a.branch_id = @UserBranchId",
        "SELECT ca.card_id FROM cards ca INNER JOIN accounts a ON ca.account_id = a.account_id WHERE a.branch_id = @UserBranchId",
        "SELECT c.customer_id FROM customers c INNER JOIN accounts a ON c.customer_id = a.customer_id WHERE a.branch_id = @UserBranchId",
        "SELECT l.loan_id FROM loans l INNER JOIN customers c ON l.customer_id = c.customer_id INNER JOIN accounts a ON c.customer_id = a.customer_id INNER JOIN branches b ON a.branch_id = b.branch_id WHERE b.branch_id = @UserBranchId",
        "SELECT m.merchant_id FROM merchants m INNER JOIN transactions t ON m.merchant_id = t.merchant_id INNER JOIN accounts a ON t.account_id = a.account_id WHERE a.branch_id = @UserBranchId",
    ]
    for sql in cases:
        assert _validator().validate(sql).is_valid, sql


def test_rejects_customer_query_without_backend_branch_path():
    result = _validator().validate("SELECT c.customer_id FROM customers c WHERE @UserBranchId IS NOT NULL")
    assert not result.is_valid
    assert result.issues[0].type == "RLS_CUSTOMERS_MAPPING_REQUIRED"
