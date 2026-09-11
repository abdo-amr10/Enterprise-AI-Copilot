"""Unit tests for authoritative security/RLS metadata flow end-to-end."""

from unittest.mock import Mock

import pytest

from src.application.pipelines.semantic_layer.semantic_layer_validation_pipeline import (
    SemanticLayerValidationPipeline,
)
from src.application.services.semantic_layer.builders.full_build_builder import (
    FullRebuildBuilder,
)
from src.application.services.semantic_layer.merge.semantic_layer_merger_service import (
    SemanticLayerMergeService,
)
from src.application.services.semantic_layer.security.security_rule_extractor import (
    SecurityRuleExtractor,
)
from src.application.services.semantic_layer.validation.semantic_layer_auto_fixer import (
    SemanticLayerAutoFixer,
)
from src.application.services.semantic_layer.validation.semantic_layer_validator import (
    SemanticLayerValidator,
)


DOCUMENTATION_MARKDOWN = """
# Database Documentation

## RLS Mapping Security & Data Filtering
| Table | Join Logic | Enforced SQL via Validation Layer |
| `branches` | Contains branch_id directly | `WHERE branches.branch_id = @UserBranchId` |
| `accounts` | Contains branch_id directly | `WHERE accounts.branch_id = @UserBranchId` |
| `transactions` | Joined with accounts table via account_id | `INNER JOIN accounts ON transactions.account_id = accounts.account_id WHERE accounts.branch_id = @UserBranchId` |
| `cards` | Joined with accounts table via account_id | `INNER JOIN accounts ON cards.account_id = accounts.account_id WHERE accounts.branch_id = @UserBranchId` |
| `customers` | Joined with accounts table via customer_id | `INNER JOIN accounts ON customers.customer_id = accounts.customer_id WHERE accounts.branch_id = @UserBranchId` |
| `loans` | Joined with customers table via customer_id | `INNER JOIN customers ON loans.customer_id = customers.customer_id INNER JOIN accounts ON customers.customer_id = accounts.customer_id WHERE accounts.branch_id = @UserBranchId` |
| `merchants` | Joined with transactions table via merchant_id | `INNER JOIN transactions ON merchants.merchant_id = transactions.merchant_id INNER JOIN accounts ON transactions.account_id = accounts.account_id WHERE accounts.branch_id = @UserBranchId` |
"""

DOCUMENTATION_BLOCK = """
RLS Mapping Security & Data Filtering

branches:
WHERE branches.branch_id = @UserBranchId

accounts:
WHERE accounts.branch_id = @UserBranchId

transactions:
INNER JOIN accounts
ON transactions.account_id = accounts.account_id
WHERE accounts.branch_id = @UserBranchId
"""

SCHEMA = {
    "tables": {
        "branches": {"columns": [{"name": "branch_id"}, {"name": "name"}]},
        "accounts": {"columns": [{"name": "account_id"}, {"name": "branch_id"}, {"name": "customer_id"}]},
        "transactions": {"columns": [{"name": "transaction_id"}, {"name": "account_id"}, {"name": "merchant_id"}]},
        "cards": {"columns": [{"name": "card_id"}, {"name": "account_id"}]},
        "customers": {"columns": [{"name": "customer_id"}, {"name": "name"}]},
        "loans": {"columns": [{"name": "loan_id"}, {"name": "customer_id"}]},
        "merchants": {"columns": [{"name": "merchant_id"}, {"name": "name"}]},
    }
}

RELATIONSHIPS = [
    {"name": "rel_acc_br", "from_table": "accounts", "from_column": "branch_id", "to_table": "branches", "to_column": "branch_id", "is_executable": True},
    {"name": "rel_tx_acc", "from_table": "transactions", "from_column": "account_id", "to_table": "accounts", "to_column": "account_id", "is_executable": True},
    {"name": "rel_cd_acc", "from_table": "cards", "from_column": "account_id", "to_table": "accounts", "to_column": "account_id", "is_executable": True},
    {"name": "rel_cust_acc", "from_table": "customers", "from_column": "customer_id", "to_table": "accounts", "to_column": "customer_id", "is_executable": True},
    {"name": "rel_loan_cust", "from_table": "loans", "from_column": "customer_id", "to_table": "customers", "to_column": "customer_id", "is_executable": True},
    {"name": "rel_merch_tx", "from_table": "merchants", "from_column": "merchant_id", "to_table": "transactions", "to_column": "merchant_id", "is_executable": True},
]


def _build_compliant_draft(trigger_type="FullRebuild"):
    extracted_rules = SecurityRuleExtractor.extract_security_rules(DOCUMENTATION_MARKDOWN)
    dimensions = []
    for tbl_name, tbl_info in SCHEMA["tables"].items():
        for col in tbl_info["columns"]:
            dimensions.append({
                "name": f"{tbl_name}_{col['name']}",
                "mapping": f"{tbl_name}.{col['name']}",
            })
    return {
        "metadata": {
            "semantic_layer_id": "SL-001",
            "revision_id": "REV-001",
            "status": "initial_draft",
            "trigger_type": trigger_type,
            "validated": False,
            "human_review_required": True,
        },
        "entities": [
            {"name": "Branch", "mapping": "branches", "security_domain": "branch"},
            {"name": "Account", "mapping": "accounts", "security_domain": "branch"},
            {"name": "Transaction", "mapping": "transactions", "security_domain": "branch"},
            {"name": "Card", "mapping": "cards", "security_domain": "branch"},
            {"name": "Customer", "mapping": "customers", "security_domain": "branch"},
            {"name": "Loan", "mapping": "loans", "security_domain": "branch"},
            {"name": "Merchant", "mapping": "merchants", "security_domain": "branch"},
        ],
        "relationships": RELATIONSHIPS,
        "measures": [],
        "dimensions": dimensions,
        "business_rules": [],
        "security_domains": extracted_rules,
        "validation_issues": [],
    }


def test_security_rule_extractor_markdown_table():
    rules = SecurityRuleExtractor.extract_security_rules(DOCUMENTATION_MARKDOWN)
    assert len(rules) == 1
    rule = rules[0]
    assert rule["name"] == "branch"
    assert rule["security_scope"] == "branch"
    assert rule["canonical_root"] == "accounts.branch_id"
    assert rule["canonical_predicate"] == "accounts.branch_id = @UserBranchId"
    assert rule["security_parameter"] == "@UserBranchId"
    assert len(rule["propagation_paths"]) == 7
    targets = {p["target_table"] for p in rule["propagation_paths"]}
    assert targets == {"branches", "accounts", "transactions", "cards", "customers", "loans", "merchants"}


def test_security_rule_extractor_block_format():
    rules = SecurityRuleExtractor.extract_security_rules(DOCUMENTATION_BLOCK)
    assert len(rules) == 1
    rule = rules[0]
    assert rule["name"] == "branch"
    assert rule["canonical_root"] == "accounts.branch_id"
    assert rule["security_parameter"] == "@UserBranchId"
    targets = {p["target_table"] for p in rule["propagation_paths"]}
    assert targets == {"branches", "accounts", "transactions"}


def test_security_rule_extractor_empty_or_non_rls():
    assert SecurityRuleExtractor.extract_security_rules(None) == []
    assert SecurityRuleExtractor.extract_security_rules("") == []
    assert SecurityRuleExtractor.extract_security_rules("No security rules here") == []


def test_validator_passes_compliant_draft():
    draft = _build_compliant_draft()
    rules = SecurityRuleExtractor.extract_security_rules(DOCUMENTATION_MARKDOWN)
    result = SemanticLayerValidator().validate(
        draft=draft,
        schema=SCHEMA,
        relationships=RELATIONSHIPS,
        authoritative_security_rules=rules,
    )
    assert result["status"] == "passed"
    assert len(result["errors"]) == 0


def test_validator_detects_missing_authoritative_security_rule():
    draft = _build_compliant_draft()
    draft["security_domains"] = []
    rules = SecurityRuleExtractor.extract_security_rules(DOCUMENTATION_MARKDOWN)
    result = SemanticLayerValidator().validate(
        draft=draft,
        schema=SCHEMA,
        relationships=RELATIONSHIPS,
        authoritative_security_rules=rules,
    )
    assert result["status"] == "failed"
    codes = {e["code"] for e in result["errors"]}
    assert "missing_authoritative_security_rule" in codes


def test_validator_detects_canonical_root_mismatch():
    draft = _build_compliant_draft()
    draft["security_domains"][0]["canonical_root"] = "branches.branch_id"
    rules = SecurityRuleExtractor.extract_security_rules(DOCUMENTATION_MARKDOWN)
    result = SemanticLayerValidator().validate(
        draft=draft,
        schema=SCHEMA,
        relationships=RELATIONSHIPS,
        authoritative_security_rules=rules,
    )
    assert result["status"] == "failed"
    codes = {e["code"] for e in result["errors"]}
    assert "canonical_root_mismatch" in codes


def test_validator_detects_canonical_predicate_mismatch():
    draft = _build_compliant_draft()
    draft["security_domains"][0]["canonical_predicate"] = "accounts.branch_id = 100"
    rules = SecurityRuleExtractor.extract_security_rules(DOCUMENTATION_MARKDOWN)
    result = SemanticLayerValidator().validate(
        draft=draft,
        schema=SCHEMA,
        relationships=RELATIONSHIPS,
        authoritative_security_rules=rules,
    )
    assert result["status"] == "failed"
    codes = {e["code"] for e in result["errors"]}
    assert "canonical_predicate_mismatch" in codes


def test_validator_detects_security_parameter_mismatch():
    draft = _build_compliant_draft()
    draft["security_domains"][0]["security_parameter"] = "@WrongParam"
    rules = SecurityRuleExtractor.extract_security_rules(DOCUMENTATION_MARKDOWN)
    result = SemanticLayerValidator().validate(
        draft=draft,
        schema=SCHEMA,
        relationships=RELATIONSHIPS,
        authoritative_security_rules=rules,
    )
    assert result["status"] == "failed"
    codes = {e["code"] for e in result["errors"]}
    assert "security_parameter_mismatch" in codes


def test_validator_detects_missing_security_target_coverage():
    draft = _build_compliant_draft()
    draft["security_domains"][0]["propagation_paths"] = [
        p for p in draft["security_domains"][0]["propagation_paths"]
        if p["target_table"] != "loans"
    ]
    rules = SecurityRuleExtractor.extract_security_rules(DOCUMENTATION_MARKDOWN)
    result = SemanticLayerValidator().validate(
        draft=draft,
        schema=SCHEMA,
        relationships=RELATIONSHIPS,
        authoritative_security_rules=rules,
    )
    assert result["status"] == "failed"
    codes = {e["code"] for e in result["errors"]}
    assert "missing_security_target_coverage" in codes


def test_validator_detects_unsupported_security_propagation_path():
    draft = _build_compliant_draft()
    draft["security_domains"][0]["propagation_paths"].append({
        "target_table": "merchants",
        "path": "merchants.invalid_id = customers.invalid_id -> customers.branch_id = @UserBranchId",
        "propagation": "allowed",
    })
    rules = SecurityRuleExtractor.extract_security_rules(DOCUMENTATION_MARKDOWN)
    result = SemanticLayerValidator().validate(
        draft=draft,
        schema=SCHEMA,
        relationships=RELATIONSHIPS,
        authoritative_security_rules=rules,
    )
    assert result["status"] == "failed"
    codes = {e["code"] for e in result["errors"]}
    assert "unsupported_security_propagation_path" in codes


def test_validator_detects_invented_security_rule():
    draft = _build_compliant_draft()
    draft["security_domains"].append({
        "name": "invented_tenant_domain",
        "canonical_root": "accounts.branch_id",
        "canonical_predicate": "accounts.branch_id = @UserBranchId",
        "security_parameter": "@UserBranchId",
        "propagation_paths": [],
    })
    rules = SecurityRuleExtractor.extract_security_rules(DOCUMENTATION_MARKDOWN)
    result = SemanticLayerValidator().validate(
        draft=draft,
        schema=SCHEMA,
        relationships=RELATIONSHIPS,
        authoritative_security_rules=rules,
    )
    assert result["status"] == "failed"
    codes = {e["code"] for e in result["errors"]}
    assert "invented_security_rule" in codes


def test_validator_detects_security_domain_undefined_for_entity():
    draft = _build_compliant_draft()
    draft["entities"][0]["security_domain"] = "nonexistent_domain"
    result = SemanticLayerValidator().validate(
        draft=draft,
        schema=SCHEMA,
        relationships=RELATIONSHIPS,
    )
    assert result["status"] == "failed"
    codes = {e["code"] for e in result["errors"]}
    assert "security_domain_undefined" in codes


def test_incremental_merge_preserves_unaffected_security_domains():
    approved = _build_compliant_draft("Incremental")
    for sec in ("entities", "relationships", "measures", "dimensions", "business_rules", "security_domains"):
        for idx, item in enumerate(approved.get(sec, [])):
            item["object_id"] = f"obj-{sec}-{idx}"

    patch = {
        "metadata": {"trigger_type": "Incremental"},
        "entities": [{"name": "AuditLog", "mapping": "audit_logs"}],
    }
    affected = [{"name": "AuditLog", "section": "entities", "action": "add"}]

    merger = SemanticLayerMergeService()
    merged = merger.merge(approved, patch, affected)

    assert "security_domains" in merged
    assert len(merged["security_domains"]) == 1
    assert merged["security_domains"][0]["object_id"] == "obj-security_domains-0"
    assert len(merged["security_domains"][0]["propagation_paths"]) == 7


def test_incremental_merge_updates_propagation_paths_by_target():
    approved = _build_compliant_draft("Incremental")
    approved["security_domains"][0]["object_id"] = "sec-dom-001"

    patch = {
        "metadata": {"trigger_type": "Incremental"},
        "security_domains": [
            {
                "object_id": "sec-dom-001",
                "name": "branch",
                "propagation_paths": [
                    {
                        "target_table": "new_table",
                        "path": "new_table.account_id = accounts.account_id -> accounts.branch_id = @UserBranchId",
                        "propagation": "allowed",
                    }
                ],
            }
        ],
    }
    affected = [{"id": "sec-dom-001", "name": "branch", "section": "security_domains", "action": "update"}]

    merger = SemanticLayerMergeService()
    merged = merger.merge(approved, patch, affected)

    dom = merged["security_domains"][0]
    assert dom["object_id"] == "sec-dom-001"
    targets = {p["target_table"] for p in dom["propagation_paths"]}
    assert "new_table" in targets
    assert "accounts" in targets
    assert "transactions" in targets
    assert len(dom["propagation_paths"]) == 8


def test_auto_fixer_preserves_identity_and_authoritative_rules():
    original = _build_compliant_draft("Incremental")
    original["metadata"]["base_revision_id"] = "REV-BASE"
    original["security_domains"][0]["object_id"] = "sec-dom-001"
    original["security_domains"][0]["propagation_paths"][0]["object_id"] = "path-001"

    corrected = _build_compliant_draft("FullRebuild")
    corrected["metadata"]["revision_id"] = "REV-NEW"

    fixed = SemanticLayerAutoFixer._preserve_identity(original, corrected)

    assert fixed["metadata"]["semantic_layer_id"] == "SL-001"
    assert fixed["metadata"]["revision_id"] == "REV-001"
    assert fixed["metadata"]["base_revision_id"] == "REV-BASE"
    assert fixed["metadata"]["trigger_type"] == "Incremental"
    assert fixed["security_domains"][0]["object_id"] == "sec-dom-001"
    assert fixed["security_domains"][0]["propagation_paths"][0]["object_id"] == "path-001"


def test_validation_pipeline_with_documentation():
    draft = _build_compliant_draft()
    pipeline = SemanticLayerValidationPipeline(
        validator=SemanticLayerValidator(), auto_fixer=Mock(), max_fix_attempts=0
    )
    final_draft, validation = pipeline.run(
        draft=draft,
        schema=SCHEMA,
        relationships=RELATIONSHIPS,
        documentation=DOCUMENTATION_MARKDOWN,
    )
    assert validation["status"] == "passed"
    assert final_draft["metadata"]["validated"] is True
    assert final_draft["metadata"]["status"] == "validated"
