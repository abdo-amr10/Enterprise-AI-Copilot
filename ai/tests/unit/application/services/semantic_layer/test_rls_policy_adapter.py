"""Unit tests for RlsPolicyAdapter and its integration across Semantic Layer & SQL RLS Validator."""

import pytest
from src.application.services.semantic_layer.security.rls_policy_adapter import (
    RlsPolicyAdapter,
)
from src.application.services.semantic_layer.validation.semantic_layer_validator import (
    SemanticLayerValidator,
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
from src.application.services.semantic_layer.merge.semantic_layer_merger_service import (
    SemanticLayerMergeService,
)


SAMPLE_BACKEND_POLICY = {
    "enabled": True,
    "userValueField": "BranchId",
    "scopeParameter": "@UserBranchId",
    "rules": [
        {
            "table": "branches",
            "scopeColumn": "branch_id",
            "type": "direct",
        },
        {
            "table": "accounts",
            "scopeColumn": "branch_id",
            "type": "direct",
        },
        {
            "table": "customers",
            "joinTable": "accounts",
            "joinFromColumn": "customer_id",
            "joinToColumn": "customer_id",
            "scopeColumn": "branch_id",
            "type": "join",
        },
        {
            "table": "transactions",
            "joinTable": "accounts",
            "joinFromColumn": "account_id",
            "joinToColumn": "account_id",
            "scopeColumn": "branch_id",
            "type": "join",
        },
    ],
}

SCHEMA_TABLES = {
    "branches": {"columns": [{"name": "branch_id"}, {"name": "name"}]},
    "accounts": {"columns": [{"name": "account_id"}, {"name": "branch_id"}, {"name": "customer_id"}]},
    "customers": {"columns": [{"name": "customer_id"}, {"name": "name"}]},
    "transactions": {"columns": [{"name": "transaction_id"}, {"name": "account_id"}, {"name": "amount"}]},
}


def test_adapter_converts_backend_policy_direct_and_join():
    domains = RlsPolicyAdapter.to_security_domains(SAMPLE_BACKEND_POLICY)

    assert len(domains) == 1
    domain = domains[0]

    assert domain["name"] == "branch"
    assert domain["security_scope"] == "branch"
    assert domain["canonical_root"] == "accounts.branch_id"
    assert domain["canonical_predicate"] == "accounts.branch_id = @UserBranchId"
    assert domain["security_parameter"] == "@UserBranchId"
    assert domain["source"] == "backend_policy"
    assert domain["authoritative"] is True

    paths = domain["propagation_paths"]
    assert len(paths) == 4

    path_by_target = {p["target_table"]: p for p in paths}
    assert "accounts" in path_by_target
    assert "branches" in path_by_target
    assert "customers" in path_by_target
    assert "transactions" in path_by_target

    accounts_path = path_by_target["accounts"]
    assert accounts_path["is_canonical_root"] is True
    assert accounts_path["path"] == "accounts.branch_id = @UserBranchId"
    assert accounts_path["predicate"] == "accounts.branch_id = @UserBranchId"
    assert accounts_path["predicate_equivalence"]["INNER JOIN"] is True

    customers_path = path_by_target["customers"]
    assert customers_path["is_canonical_root"] is False
    assert (
        customers_path["path"]
        == "customers.customer_id = accounts.customer_id -> accounts.branch_id = @UserBranchId"
    )
    assert customers_path["predicate"] == "accounts.branch_id = @UserBranchId"
    assert len(customers_path["joins"]) == 1
    assert customers_path["joins"][0]["table"] == "accounts"
    assert customers_path["joins"][0]["condition"] == "customers.customer_id = accounts.customer_id"


def test_adapter_handles_disabled_or_empty():
    assert RlsPolicyAdapter.to_security_domains({"enabled": False}) == []
    assert RlsPolicyAdapter.to_security_domains({}) == []
    assert RlsPolicyAdapter.to_security_domains(None) == []
    assert RlsPolicyAdapter.to_security_domains("") == []
    assert RlsPolicyAdapter.to_security_domains({"enabled": True, "rules": []}) == []


def test_adapter_output_passes_semantic_layer_validator():
    domains = RlsPolicyAdapter.to_security_domains(SAMPLE_BACKEND_POLICY)
    errors = []
    warnings = []

    SemanticLayerValidator._check_security_domains(
        items=domains,
        tables=SCHEMA_TABLES,
        warnings=warnings,
        errors=errors,
    )

    assert errors == [], f"Validation errors found: {errors}"
    assert warnings == [], f"Validation warnings found: {warnings}"


class _MockSchemaProvider:
    def __init__(self, security_domains):
        self._security_domains = security_domains

    def get_schema(self):
        return {
            "tables": {name: {"columns": []} for name in SCHEMA_TABLES},
            "security_domains": self._security_domains,
        }


def test_adapter_output_validates_with_sql_rls_validator():
    domains = RlsPolicyAdapter.to_security_domains(SAMPLE_BACKEND_POLICY)
    syntax = SQLSyntaxValidator()
    provider = _MockSchemaProvider(domains)
    schema_val = SQLSchemaValidator(provider, syntax)
    validator = SQLRlsValidator(syntax, schema_val)

    # 1. Valid accounts query
    valid_acc = validator.validate("SELECT a.account_id FROM accounts a WHERE a.branch_id = @UserBranchId")
    assert valid_acc.is_valid

    # 2. Valid joined customers query
    valid_cust = validator.validate(
        "SELECT c.name FROM customers c INNER JOIN accounts a ON c.customer_id = a.customer_id WHERE a.branch_id = @UserBranchId"
    )
    assert valid_cust.is_valid

    # 3. Invalid customers query without join to accounts
    invalid_cust = validator.validate("SELECT c.name FROM customers c WHERE @UserBranchId IS NOT NULL")
    assert not invalid_cust.is_valid
    assert invalid_cust.issues[0].type == "RLS_CUSTOMERS_MAPPING_REQUIRED"


def test_incremental_merge_with_adapted_rls_policy():
    initial_domains = RlsPolicyAdapter.to_security_domains({
        "enabled": True,
        "userValueField": "BranchId",
        "scopeParameter": "@UserBranchId",
        "rules": [
            {"table": "accounts", "scopeColumn": "branch_id", "type": "direct"},
        ]
    })
    initial_domains[0]["object_id"] = "sec-dom-001"

    base_layer = {
        "metadata": {"semantic_layer_id": "SL-001", "revision_id": "REV-001"},
        "entities": [],
        "relationships": [],
        "measures": [],
        "dimensions": [],
        "business_rules": [],
        "security_domains": initial_domains,
    }

    # New policy adds customers rule
    updated_policy = {
        "enabled": True,
        "userValueField": "BranchId",
        "scopeParameter": "@UserBranchId",
        "rules": [
            {"table": "accounts", "scopeColumn": "branch_id", "type": "direct"},
            {
                "table": "customers",
                "joinTable": "accounts",
                "joinFromColumn": "customer_id",
                "joinToColumn": "customer_id",
                "scopeColumn": "branch_id",
                "type": "join"
            }
        ]
    }
    updated_domains = RlsPolicyAdapter.to_security_domains(updated_policy)
    incremental_layer = {
        "metadata": {"semantic_layer_id": "SL-001", "revision_id": "REV-002"},
        "entities": [],
        "relationships": [],
        "measures": [],
        "dimensions": [],
        "business_rules": [],
        "security_domains": updated_domains,
    }

    merger = SemanticLayerMergeService()
    merged = merger.merge(
        approved_layer=base_layer,
        incremental_layer=incremental_layer,
        affected_objects=[
            {"id": "sec-dom-001", "name": "branch", "section": "security_domains", "action": "update"}
        ]
    )

    assert len(merged["security_domains"]) == 1
    assert len(merged["security_domains"][0]["propagation_paths"]) == 2
    targets = {p["target_table"] for p in merged["security_domains"][0]["propagation_paths"]}
    assert targets == {"accounts", "customers"}


def test_adapter_handles_generic_retail_store_policy_and_branch_mapping():
    retail_policy = {
        "enabled": True,
        "branchMapping": "store_id",
        "rules": [
            {"table": "stores", "scopeColumn": "store_id", "type": "direct"},
            {
                "table": "orders",
                "joinTable": "stores",
                "joinFromColumn": "store_id",
                "joinToColumn": "store_id",
                "scopeColumn": "store_id",
                "type": "join",
            },
        ],
    }
    domains = RlsPolicyAdapter.to_security_domains(retail_policy)
    assert len(domains) == 1
    d = domains[0]
    assert d["name"] == "store"
    assert d["security_scope"] == "store"
    assert d["security_parameter"] == "@UserStoreId"
    assert d["canonical_root"] == "stores.store_id"
    assert d["branch_mapping"] == "store_id"
    assert d["scope_mapping"] == "store_id"

