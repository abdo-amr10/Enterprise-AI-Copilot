import pytest
from src.application.services.self_correction.validators.sql_rls_validator import (
    SQLRlsValidator,
)
from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)


class _MockSemanticRepo:
    def __init__(self, security_domains):
        self._security_domains = security_domains

    def load(self):
        return {"security_domains": self._security_domains}


class _MockSchemaRepo:
    def get_schema(self):
        return {
            "tables": {
                "organizations": {"columns": [{"name": "org_id"}]},
                "departments": {
                    "columns": [{"name": "dept_id"}, {"name": "org_id"}]
                },
                "employees": {
                    "columns": [
                        {"name": "emp_id"},
                        {"name": "dept_id"},
                        {"name": "salary"},
                    ]
                },
                "projects": {"columns": [{"name": "proj_id"}, {"name": "name"}]},
                "unprotected_logs": {
                    "columns": [{"name": "log_id"}, {"name": "msg"}]
                },
            }
        }


def _create_dynamic_validator(security_domains):
    syntax = SQLSyntaxValidator()
    schema = SQLSchemaValidator(_MockSchemaRepo(), syntax)
    repo = _MockSemanticRepo(security_domains)
    return SQLRlsValidator(syntax, schema, semantic_repository=repo)


def test_unprotected_table_passes_without_security_params():
    domains = [
        {
            "name": "org_isolation",
            "canonical_root": "departments.org_id",
            "canonical_predicate": "departments.org_id = @TenantId",
            "propagation_paths": [
                {
                    "target_table": "departments",
                    "path": "departments.org_id = @TenantId",
                    "propagation": "allowed",
                    "is_canonical_root": True,
                },
                {
                    "target_table": "employees",
                    "path": "employees.dept_id = departments.dept_id -> departments.org_id = @TenantId",
                    "propagation": "allowed",
                },
            ],
        }
    ]
    validator = _create_dynamic_validator(domains)
    sql = "SELECT log_id, msg FROM unprotected_logs"
    res = validator.validate(sql)
    assert res.is_valid


def test_synthetic_tenant_domain_direct_filter_passes():
    domains = [
        {
            "name": "org_isolation",
            "canonical_root": "departments.org_id",
            "canonical_predicate": "departments.org_id = @TenantId",
            "propagation_paths": [
                {
                    "target_table": "departments",
                    "path": "departments.org_id = @TenantId",
                    "propagation": "allowed",
                    "is_canonical_root": True,
                }
            ],
        }
    ]
    validator = _create_dynamic_validator(domains)
    sql = "SELECT d.dept_id FROM departments AS d WHERE d.org_id = @TenantId"
    res = validator.validate(sql)
    assert res.is_valid


def test_synthetic_tenant_domain_missing_param_fails():
    domains = [
        {
            "name": "org_isolation",
            "canonical_root": "departments.org_id",
            "canonical_predicate": "departments.org_id = @TenantId",
            "propagation_paths": [
                {
                    "target_table": "departments",
                    "path": "departments.org_id = @TenantId",
                    "propagation": "allowed",
                    "is_canonical_root": True,
                }
            ],
        }
    ]
    validator = _create_dynamic_validator(domains)
    sql = "SELECT d.dept_id FROM departments AS d WHERE d.org_id = 123"
    res = validator.validate(sql)
    assert not res.is_valid
    assert res.issues[0].type == "RLS_PARAMETER_MISSING"


def test_synthetic_tenant_propagation_path_validation():
    domains = [
        {
            "name": "org_isolation",
            "canonical_root": "departments.org_id",
            "canonical_predicate": "departments.org_id = @TenantId",
            "propagation_paths": [
                {
                    "target_table": "departments",
                    "path": "departments.org_id = @TenantId",
                    "propagation": "allowed",
                    "is_canonical_root": True,
                },
                {
                    "target_table": "employees",
                    "path": "employees.dept_id = departments.dept_id -> departments.org_id = @TenantId",
                    "propagation": "allowed",
                },
            ],
        }
    ]
    validator = _create_dynamic_validator(domains)

    # Valid join path: employees -> departments with @TenantId filter
    valid_sql = (
        "SELECT e.emp_id, e.salary FROM employees AS e "
        "INNER JOIN departments AS d ON e.dept_id = d.dept_id "
        "WHERE d.org_id = @TenantId"
    )
    assert validator.validate(valid_sql).is_valid

    # Missing required join to departments
    invalid_sql = "SELECT e.emp_id, e.salary FROM employees AS e WHERE @TenantId = @TenantId"
    invalid_res = validator.validate(invalid_sql)
    assert not invalid_res.is_valid
    assert invalid_res.issues[0].type == "RLS_EMPLOYEES_MAPPING_REQUIRED"


def test_disallowed_propagation_path_rejected():
    domains = [
        {
            "name": "org_isolation",
            "canonical_root": "departments.org_id",
            "canonical_predicate": "departments.org_id = @TenantId",
            "propagation_paths": [
                {
                    "target_table": "projects",
                    "path": "projects -> departments",
                    "propagation": "not_allowed",
                }
            ],
        }
    ]
    validator = _create_dynamic_validator(domains)
    sql = "SELECT p.proj_id FROM projects AS p WHERE @TenantId = 1"
    res = validator.validate(sql)
    assert not res.is_valid
    assert res.issues[0].type == "RLS_PATH_NOT_ALLOWED"
