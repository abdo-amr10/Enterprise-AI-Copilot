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
