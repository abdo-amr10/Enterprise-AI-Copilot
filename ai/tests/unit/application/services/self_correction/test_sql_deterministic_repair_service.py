from src.application.services.self_correction.sql_deterministic_repair_service import (
    SQLDeterministicRepairService,
)
from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)


class _Schema:
    def get_schema(self):
        return {
            "tables": {
                "accounts": {"columns": [{"name": "customer_id"}, {"name": "branch_id"}]},
                "customers": {"columns": [{"name": "customer_id"}]},
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


def test_deterministic_repair_injects_missing_branch_id():
    syntax = SQLSyntaxValidator()
    schema = SQLSchemaValidator(_Schema(), syntax)
    repair_svc = SQLDeterministicRepairService(syntax, schema)

    candidate_sql = (
        "SELECT TOP 10 c.first_name, c.last_name, SUM(a.balance_usd) AS total_balance "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE c.credit_score > 700 "
        "GROUP BY c.customer_id, c.first_name, c.last_name "
        "ORDER BY total_balance DESC"
    )

    repaired = repair_svc.repair(candidate_sql, schema=_Schema().get_schema(), enforce_rls=True)
    assert "@UserBranchId" in repaired
    assert "a.branch_id = @UserBranchId" in repaired


def test_deterministic_repair_injects_propagation_join():
    syntax = SQLSyntaxValidator()
    schema = SQLSchemaValidator(_Schema(), syntax)
    repair_svc = SQLDeterministicRepairService(syntax, schema)

    candidate_sql = "SELECT c.customer_id, c.first_name FROM customers AS c WHERE c.credit_score > 700"
    repaired = repair_svc.repair(candidate_sql, schema=_Schema().get_schema(), enforce_rls=True)

    assert "@UserBranchId" in repaired
    assert "INNER JOIN accounts" in repaired
    assert "c.customer_id = a.customer_id" in repaired or "c.customer_id = accounts.customer_id" in repaired
    assert "branch_id = @UserBranchId" in repaired
    assert "IN (SELECT" not in repaired


def test_deterministic_repair_bridges_unapproved_indirect_join():
    syntax = SQLSyntaxValidator()
    mock_schema = {
        "tables": {
            "loans": {"columns": [{"name": "loan_id"}, {"name": "customer_id"}]},
            "accounts": {"columns": [{"name": "account_id"}, {"name": "customer_id"}]},
            "customers": {"columns": [{"name": "customer_id"}]},
        },
        "relationships": [
            {
                "from_table": "customers",
                "from_column": "customer_id",
                "to_table": "loans",
                "to_column": "customer_id",
            },
            {
                "from_table": "customers",
                "from_column": "customer_id",
                "to_table": "accounts",
                "to_column": "customer_id",
            },
        ],
    }

    class _MockRepo:
        def get_schema(self):
            return mock_schema

    schema = SQLSchemaValidator(_MockRepo(), syntax)
    repair_svc = SQLDeterministicRepairService(syntax, schema)

    # Bad query with unapproved direct join between loans and accounts
    bad_sql = (
        "SELECT l.loan_id, a.account_id "
        "FROM loans AS l "
        "INNER JOIN accounts AS a ON l.customer_id = a.customer_id"
    )

    repaired = repair_svc.repair(bad_sql, schema=mock_schema, enforce_rls=False)

    # Must have introduced customers as a bridge and re-routed joins
    assert "customers" in repaired.lower()
    # Check that loans is joined to customers and customers is joined to accounts
    assert "l.customer_id = c.customer_id" in repaired or "c.customer_id = l.customer_id" in repaired
    assert "c.customer_id = a.customer_id" in repaired or "a.customer_id = c.customer_id" in repaired

    # Verify that the SQLRelationshipValidator now marks this query as completely valid
    from src.application.services.self_correction.validators.sql_relationship_validator import (
        SQLRelationshipValidator,
    )
    rel_validator = SQLRelationshipValidator(None, syntax, schema)
    val_res = rel_validator.validate(repaired, schema=mock_schema)
    assert val_res.is_valid, f"Expected repaired query to be valid, but got issues: {[i.message for i in val_res.issues]}"


def test_deterministic_repair_multi_hop_loans_rls():
    syntax = SQLSyntaxValidator()
    mock_schema = {
        "tables": {
            "branches": {"columns": [{"name": "branch_id"}, {"name": "branch_name"}]},
            "accounts": {"columns": [{"name": "account_id"}, {"name": "customer_id"}, {"name": "branch_id"}, {"name": "balance_usd"}]},
            "customers": {"columns": [{"name": "customer_id"}, {"name": "first_name"}]},
            "loans": {"columns": [{"name": "loan_id"}, {"name": "customer_id"}]},
        },
        "relationships": [
            {"from_table": "customers", "from_column": "customer_id", "to_table": "loans", "to_column": "customer_id"},
            {"from_table": "customers", "from_column": "customer_id", "to_table": "accounts", "to_column": "customer_id"},
            {"from_table": "branches", "from_column": "branch_id", "to_table": "accounts", "to_column": "branch_id"},
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
                        "predicate_equivalence": {"INNER JOIN": True},
                    },
                    {
                        "target_table": "customers",
                        "path": "customers.customer_id = accounts.customer_id -> accounts.branch_id = @UserBranchId",
                        "propagation": "allowed",
                    },
                    {
                        "target_table": "loans",
                        "path": "loans.customer_id = customers.customer_id -> customers.customer_id = accounts.customer_id -> accounts.branch_id = branches.branch_id -> branches.branch_id = @UserBranchId",
                        "propagation": "allowed",
                        "predicate_equivalence": {"INNER JOIN": True},
                    },
                ],
            }
        ],
    }

    class _MockRepo:
        def get_schema(self):
            return mock_schema

    schema = SQLSchemaValidator(_MockRepo(), syntax)
    from src.application.services.self_correction.validators.sql_rls_validator import SQLRlsValidator
    rls_val = SQLRlsValidator(syntax, schema)
    repair_svc = SQLDeterministicRepairService(syntax, schema, rls_validator=rls_val)

    # Query bridging loans and accounts via customers, but missing the final branch join required by loans
    candidate_sql = (
        "SELECT l.loan_id, c.first_name, a.balance_usd "
        "FROM loans AS l "
        "INNER JOIN customers AS c ON l.customer_id = c.customer_id "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE a.branch_id = @UserBranchId"
    )

    repaired = repair_svc.repair(candidate_sql, schema=mock_schema, enforce_rls=True)

    # Branches must have been joined to satisfy the 4-segment path
    assert "branches" in repaired.lower()
    assert "@UserBranchId" in repaired

    # Repaired query must pass deterministic SQLRlsValidator completely
    res = rls_val.validate(repaired, schema=mock_schema)
    assert res.is_valid, f"Expected repaired query to pass RLS, but got issues: {[i.message for i in res.issues]}"


def test_deterministic_repair_nested_subquery_scope_rls():
    syntax = SQLSyntaxValidator()
    mock_schema = {
        "tables": {
            "accounts": {"columns": [{"name": "account_id"}, {"name": "customer_id"}, {"name": "branch_id"}]},
            "customers": {"columns": [{"name": "customer_id"}, {"name": "credit_score"}]},
        },
        "relationships": [
            {"from_table": "customers", "from_column": "customer_id", "to_table": "accounts", "to_column": "customer_id"},
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
                        "target_table": "customers",
                        "path": "customers.customer_id = accounts.customer_id -> accounts.branch_id = @UserBranchId",
                        "propagation": "allowed",
                    },
                ],
            }
        ],
    }

    class _MockRepo:
        def get_schema(self):
            return mock_schema

    schema = SQLSchemaValidator(_MockRepo(), syntax)
    from src.application.services.self_correction.validators.sql_rls_validator import SQLRlsValidator
    rls_val = SQLRlsValidator(syntax, schema)
    repair_svc = SQLDeterministicRepairService(syntax, schema, rls_validator=rls_val)

    candidate_sql = (
        "SELECT c.customer_id, c.credit_score "
        "FROM customers AS c "
        "INNER JOIN accounts AS a ON c.customer_id = a.customer_id "
        "WHERE a.branch_id = @UserBranchId "
        "AND c.credit_score > (SELECT AVG(c2.credit_score) FROM customers AS c2)"
    )

    repaired = repair_svc.repair(candidate_sql, schema=mock_schema, enforce_rls=True)

    # Both outer query and inner subquery must be valid
    res = rls_val.validate(repaired, schema=mock_schema)
    assert res.is_valid, f"Expected repaired nested query to pass RLS, but got issues: {[i.message for i in res.issues]}"


def test_deterministic_repair_cte_scope_rls():
    syntax = SQLSyntaxValidator()
    mock_schema = {
        "tables": {
            "accounts": {"columns": [{"name": "account_id"}, {"name": "customer_id"}, {"name": "branch_id"}]},
            "customers": {"columns": [{"name": "customer_id"}]},
        },
        "relationships": [
            {"from_table": "customers", "from_column": "customer_id", "to_table": "accounts", "to_column": "customer_id"},
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
                        "target_table": "customers",
                        "path": "customers.customer_id = accounts.customer_id -> accounts.branch_id = @UserBranchId",
                        "propagation": "allowed",
                    },
                ],
            }
        ],
    }

    class _MockRepo:
        def get_schema(self):
            return mock_schema

    schema = SQLSchemaValidator(_MockRepo(), syntax)
    from src.application.services.self_correction.validators.sql_rls_validator import SQLRlsValidator
    rls_val = SQLRlsValidator(syntax, schema)
    repair_svc = SQLDeterministicRepairService(syntax, schema, rls_validator=rls_val)

    candidate_sql = (
        "WITH customer_data AS ("
        "    SELECT c.customer_id FROM customers AS c"
        ") "
        "SELECT cd.customer_id FROM customer_data AS cd"
    )

    repaired = repair_svc.repair(candidate_sql, schema=mock_schema, enforce_rls=True)

    res = rls_val.validate(repaired, schema=mock_schema)
    assert res.is_valid, f"Expected repaired CTE query to pass RLS, but got issues: {[i.message for i in res.issues]}"


def test_deterministic_repair_dynamically_synthesizes_parameter_from_any_domain():
    syntax = SQLSyntaxValidator()
    mock_schema = {
        "tables": {
            "stores": {"columns": [{"name": "store_id"}, {"name": "store_name"}]},
            "inventories": {"columns": [{"name": "inventory_id"}, {"name": "store_id"}]},
        },
        "security_domains": [
            {
                "name": "store_domain",
                "canonical_root": "stores.store_id",
                # Omit canonical_predicate parameter to test dynamic derivation
            }
        ],
    }

    class _MockRepo:
        def get_schema(self):
            return mock_schema

    schema = SQLSchemaValidator(_MockRepo(), syntax)
    repair_svc = SQLDeterministicRepairService(syntax, schema)

    candidate_sql = "SELECT s.store_name FROM stores AS s"
    repaired = repair_svc.repair(candidate_sql, schema=mock_schema, enforce_rls=True)
    assert "@UserStoreId" in repaired
    assert "s.store_id = @UserStoreId" in repaired



