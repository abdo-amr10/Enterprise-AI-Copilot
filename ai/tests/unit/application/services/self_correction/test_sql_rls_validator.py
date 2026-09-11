from src.application.services.self_correction.validators.sql_rls_validator import SQLRlsValidator
from src.application.services.self_correction.validators.sql_schema_validator import SQLSchemaValidator
from src.application.services.self_correction.validators.sql_syntax_validator import SQLSyntaxValidator


class _Schema:
    def get_schema(self):
        return {
            "tables": {
                name: {"columns": []}
                for name in (
                    "branches",
                    "accounts",
                    "transactions",
                    "cards",
                    "customers",
                    "loans",
                    "merchants",
                )
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
                            "predicate_equivalence": {"INNER JOIN": True},
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
        "SELECT c.first_name, c.last_name, c.email, c.city FROM customers AS c WHERE c.customer_id IN (SELECT customer_id FROM accounts WHERE branch_id = @UserBranchId)",
        "SELECT l.loan_id FROM loans l INNER JOIN customers c ON l.customer_id = c.customer_id INNER JOIN accounts a ON c.customer_id = a.customer_id INNER JOIN branches b ON a.branch_id = b.branch_id WHERE b.branch_id = @UserBranchId",
        "SELECT m.merchant_id FROM merchants m INNER JOIN transactions t ON m.merchant_id = t.merchant_id INNER JOIN accounts a ON t.account_id = a.account_id WHERE a.branch_id = @UserBranchId",
    ]
    for sql in cases:
        assert _validator().validate(sql).is_valid, sql


def test_rejects_customer_query_without_backend_branch_path():
    result = _validator().validate("SELECT c.customer_id FROM customers c WHERE @UserBranchId IS NOT NULL")
    assert not result.is_valid
    assert result.issues[0].type == "RLS_CUSTOMERS_MAPPING_REQUIRED"


def test_rejects_nested_subquery_without_scope_rls():
    """Test 1: Outer valid + nested un-isolated subquery -> FAIL"""
    sql = """
    SELECT c.customer_id, c.credit_score
    FROM customers c
    INNER JOIN accounts a ON c.customer_id = a.customer_id
    WHERE a.branch_id = @UserBranchId
      AND c.credit_score > (SELECT AVG(c2.credit_score) FROM customers c2)
    """
    result = _validator().validate(sql)
    assert not result.is_valid
    assert result.issues[0].type in {"RLS_PARAMETER_MISSING", "RLS_CUSTOMERS_MAPPING_REQUIRED"}


def test_accepts_nested_subquery_with_scope_rls():
    """Test 2: Outer valid + nested isolated subquery -> PASS"""
    sql = """
    SELECT c.customer_id, c.credit_score
    FROM customers c
    INNER JOIN accounts a ON c.customer_id = a.customer_id
    WHERE a.branch_id = @UserBranchId
      AND c.credit_score > (
          SELECT AVG(c2.credit_score)
          FROM customers c2
          INNER JOIN accounts a2 ON c2.customer_id = a2.customer_id
          WHERE a2.branch_id = @UserBranchId
      )
    """
    result = _validator().validate(sql)
    assert result.is_valid


def test_rejects_deeply_nested_unisolated_subquery():
    """Test 3: Multi-level nesting with an un-isolated level -> FAIL"""
    sql = """
    SELECT a.account_id FROM accounts a
    WHERE a.branch_id = @UserBranchId
      AND a.balance_usd > (
          SELECT AVG(a2.balance_usd) FROM accounts a2
          WHERE a2.branch_id = @UserBranchId
            AND a2.customer_id IN (
                SELECT c3.customer_id FROM customers c3
            )
      )
    """
    result = _validator().validate(sql)
    assert not result.is_valid


def test_rejects_unisolated_cte_body():
    """Test 4: CTE body accessing protected tables without RLS -> FAIL"""
    sql = """
    WITH customer_data AS (
        SELECT c.customer_id FROM customers c
    )
    SELECT * FROM customer_data
    """
    result = _validator().validate(sql)
    assert not result.is_valid


def test_rejects_unisolated_derived_table():
    """Test 5: Derived table accessing protected tables without RLS -> FAIL"""
    sql = "SELECT * FROM (SELECT * FROM customers) c"
    result = _validator().validate(sql)
    assert not result.is_valid


def test_rejects_union_with_unisolated_branch():
    """Test 6: UNION with one un-isolated branch -> FAIL"""
    sql = """
    SELECT account_id FROM accounts WHERE branch_id = @UserBranchId
    UNION
    SELECT customer_id FROM customers
    """
    result = _validator().validate(sql)
    assert not result.is_valid


def test_rejects_union_all_with_unisolated_branch():
    """Test 7: UNION ALL with one un-isolated branch -> FAIL"""
    sql = """
    SELECT account_id FROM accounts WHERE branch_id = @UserBranchId
    UNION ALL
    SELECT customer_id FROM customers
    """
    result = _validator().validate(sql)
    assert not result.is_valid


def test_accepts_complex_multi_scope_valid_query():
    """Test 8: Complex statement with CTE, outer query, and nested subquery all valid -> PASS"""
    sql = """
    WITH ValidCte AS (
        SELECT c.customer_id, a.balance_usd
        FROM customers c
        INNER JOIN accounts a ON c.customer_id = a.customer_id
        WHERE a.branch_id = @UserBranchId
    )
    SELECT customer_id FROM ValidCte
    UNION ALL
    SELECT a.account_id FROM accounts a
    WHERE a.branch_id = @UserBranchId
      AND a.balance_usd > (
          SELECT AVG(a2.balance_usd)
          FROM accounts a2
          WHERE a2.branch_id = @UserBranchId
      )
    """
    result = _validator().validate(sql)
    assert result.is_valid
