"""Unit test suite for Semantic Layer Audit, Hardening & Dynamic Governance.

Tests A through J (and additional K through R) verify explicit relationship metadata,
cardinality, natural grain, distinct semantics, security domain propagation,
join-type-aware predicate equivalence, independent 1:N paths, and join-complete retrieval.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)
from src.application.services.semantic_layer.validation.semantic_layer_validator import (
    SemanticLayerValidator,
)
from src.infrastructure.semantic_layer.retrieval.semantic_document_builder import (
    SemanticDocumentBuilder,
)


_AI_ROOT = Path(__file__).resolve().parents[5]
_APPROVED_LAYER_PATH = _AI_ROOT / "outputs" / "semantic_layer" / "approved_semantic_layer.json"


def _load_approved_layer() -> dict[str, Any]:
    with _APPROVED_LAYER_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


class MockSemanticRepository:
    """Mock repository loaded with the approved semantic layer."""

    def __init__(self, layer: dict[str, Any] | None = None) -> None:
        self._layer = layer if layer is not None else _load_approved_layer()
        self.requested_top_k: int | None = None

    def load(self) -> dict[str, Any]:
        return self._layer

    def retrieve(self, question: str, top_k: int) -> list[dict[str, Any]]:
        self.requested_top_k = top_k
        q_lower = question.lower()
        docs = []
        for entity in self._layer.get("entities", []):
            if entity["mapping"] in q_lower or entity["name"].lower() in q_lower:
                docs.append({"type": "entity", "payload": entity})
        for dim in self._layer.get("dimensions", []):
            table = dim["mapping"].split(".")[0]
            if table in q_lower or dim["name"].lower() in q_lower:
                docs.append({"type": "dimension", "payload": dim})
        for measure in self._layer.get("measures", []):
            table = measure["mapping"].split(".")[0]
            if table in q_lower or measure["name"].lower() in q_lower:
                docs.append({"type": "measure", "payload": measure})
        for rule in self._layer.get("business_rules", []):
            docs.append({"type": "business_rule", "payload": rule})
        return docs[:top_k]


# ==============================================================================
# TEST A: Branch / Account Relationship Metadata
# ==============================================================================
def test_a_branch_account_relationship_metadata() -> None:
    layer = _load_approved_layer()
    relationships = {r["name"]: r for r in layer.get("relationships", [])}

    assert "branches_accounts" in relationships
    rel = relationships["branches_accounts"]

    assert rel["from_table"] == "branches"
    assert rel["from_column"] == "branch_id"
    assert rel["to_table"] == "accounts"
    assert rel["to_column"] == "branch_id"
    assert rel["source_table"] == "branches"
    assert rel["source_column"] == "branch_id"
    assert rel["target_table"] == "accounts"
    assert rel["target_column"] == "branch_id"
    assert rel["cardinality"] == "1:N"
    assert rel["relationship_type"] == "foreign_key"
    assert rel["nullable"] is False
    assert rel["security_propagation"] == "allowed"

    # Predicate equivalence must be join-type aware
    pred_eq = rel["predicate_equivalence"]
    assert isinstance(pred_eq, dict)
    assert pred_eq.get("INNER JOIN") is True
    assert pred_eq.get("FULL JOIN") is False


# ==============================================================================
# TEST B: Account / Transaction Relationship Metadata
# ==============================================================================
def test_b_account_transaction_relationship_metadata() -> None:
    layer = _load_approved_layer()
    relationships = {r["name"]: r for r in layer.get("relationships", [])}

    assert "accounts_transactions" in relationships
    rel = relationships["accounts_transactions"]

    assert rel["from_table"] == "accounts"
    assert rel["from_column"] == "account_id"
    assert rel["to_table"] == "transactions"
    assert rel["to_column"] == "account_id"
    assert rel["cardinality"] == "1:N"
    assert rel["relationship_type"] == "foreign_key"
    assert rel["security_propagation"] == "allowed"
    assert rel["fanout_risk"] is True


# ==============================================================================
# TEST C: Account / Customer Relationship Metadata
# ==============================================================================
def test_c_account_customer_relationship_metadata() -> None:
    layer = _load_approved_layer()
    relationships = {r["name"]: r for r in layer.get("relationships", [])}

    assert "customers_accounts" in relationships
    rel = relationships["customers_accounts"]

    assert rel["from_table"] == "customers"
    assert rel["from_column"] == "customer_id"
    assert rel["to_table"] == "accounts"
    assert rel["to_column"] == "customer_id"
    assert rel["cardinality"] == "1:N"
    assert rel["relationship_type"] == "foreign_key"
    assert rel["security_propagation"] == "allowed"


# ==============================================================================
# TEST D: Security Propagation Representation
# ==============================================================================
def test_d_security_propagation_representation() -> None:
    layer = _load_approved_layer()
    repo = MockSemanticRepository(layer)
    service = ContextRetrievalService(repo)

    context = service.build_llm_context("Show transactions for customer accounts")

    assert "SECURITY DOMAIN & CANONICAL SECURITY SCOPE:" in context
    assert "Security domain: branch" in context
    assert "Canonical security root: accounts.branch_id = @UserBranchId" in context
    assert "transactions" in context
    assert "propagation: allowed" in context


# ==============================================================================
# TEST E: RLS Predicate Equivalence Join-Type Awareness
# ==============================================================================
def test_e_rls_predicate_equivalence_join_type_aware() -> None:
    layer = _load_approved_layer()
    relationships = {r["name"]: r for r in layer.get("relationships", [])}
    rel = relationships["branches_accounts"]

    pred_eq = rel["predicate_equivalence"]
    assert isinstance(pred_eq, dict)
    assert pred_eq["INNER JOIN"] is True
    assert pred_eq["LEFT JOIN"] != True or pred_eq["LEFT JOIN"] == "conditional"
    assert pred_eq["FULL JOIN"] is False


# ==============================================================================
# TEST F: Independent One-to-Many Paths & Fanout Risk
# ==============================================================================
def test_f_independent_one_to_many_paths_detection() -> None:
    layer = _load_approved_layer()
    repo = MockSemanticRepository(layer)
    service = ContextRetrievalService(repo)

    # Multi-path scope: accounts -> transactions (1:N) and accounts -> cards (1:N)
    context_multi = service.build_llm_context("Show accounts with transactions and cards")
    assert "Independent 1:N child paths detected" in context_multi
    assert "Fanout risk: true" in context_multi
    assert "Requires pre-aggregation: true" in context_multi
    assert "SAFE AGGREGATION:" in context_multi

    # Single path scope: branches -> accounts (1:N only)
    context_single = service.build_llm_context("Show branch accounts")
    assert "Fanout risk: false" in context_single
    assert "Requires pre-aggregation: false" in context_single


# ==============================================================================
# TEST G: DISTINCT Measure Semantics
# ==============================================================================
def test_g_distinct_measure_semantics() -> None:
    layer = _load_approved_layer()
    measures = {m["name"]: m for m in layer.get("measures", [])}

    assert "Customer Count" in measures
    cust_count = measures["Customer Count"]
    assert cust_count["distinct_required"] is True
    assert cust_count["distinct_key"] == "customer_id"
    assert cust_count["natural_entity"] == "Customer"
    assert cust_count["aggregation_function"] == "COUNT DISTINCT"

    # Transaction Volume does NOT force DISTINCT
    assert "Transaction Volume" in measures
    vol = measures["Transaction Volume"]
    assert vol["distinct_required"] is False
    assert vol["aggregation_function"] == "SUM"


# ==============================================================================
# TEST H: Transaction Measure Natural Grain
# ==============================================================================
def test_h_transaction_measure_natural_grain() -> None:
    layer = _load_approved_layer()
    measures = {m["name"]: m for m in layer.get("measures", [])}

    vol = measures["Transaction Volume"]
    assert vol["mapping"] == "transactions.amount_usd"
    assert vol["source_table"] == "transactions"
    assert vol["source_column"] == "amount_usd"
    assert vol["natural_grain"] == "transaction"
    assert vol["natural_entity"] == "Transaction"
    assert vol["aggregation_function"] == "SUM"
    assert vol["fanout_sensitive"] is True


# ==============================================================================
# TEST I: Join-Complete Retrieval
# ==============================================================================
def test_i_join_complete_retrieval() -> None:
    layer = _load_approved_layer()
    repo = MockSemanticRepository(layer)
    service = ContextRetrievalService(repo)

    context = service.build_llm_context(
        "Show branches, accounts, transactions, and customers"
    )

    assert "TABLE: branches" in context
    assert "TABLE: accounts" in context
    assert "TABLE: transactions" in context
    assert "TABLE: customers" in context

    assert "branches.branch_id -> accounts.branch_id" in context
    assert "accounts.account_id -> transactions.account_id" in context
    assert "customers.customer_id -> accounts.customer_id" in context
    assert "cardinality: 1:N" in context
    assert "security_propagation: allowed" in context
    assert "QUERY SCOPE:" in context


# ==============================================================================
# TEST J: Unknown Cardinality Is Preserved Not Guessed
# ==============================================================================
def test_j_unknown_cardinality_preserved() -> None:
    layer = _load_approved_layer()
    layer["relationships"].append({
        "name": "custom_unknown_rel",
        "from_table": "customers",
        "from_column": "city",
        "to_table": "branches",
        "to_column": "city",
        "cardinality": "unknown",
        "relationship_type": "attribute_match",
    })

    repo = MockSemanticRepository(layer)
    service = ContextRetrievalService(repo)

    context = service.build_llm_context("Show customers in branch city")

    assert "cardinality: unknown" in context
    assert "cardinality: 1:1" not in context.split("custom_unknown_rel")[0]


# ==============================================================================
# TEST K: LEFT JOIN Security Semantics Not Equated to INNER JOIN
# ==============================================================================
def test_k_left_join_security_semantics() -> None:
    layer = _load_approved_layer()
    relationships = {r["name"]: r for r in layer.get("relationships", [])}
    rel = relationships["branches_accounts"]

    assert rel["predicate_equivalence"]["INNER JOIN"] is True
    assert rel["predicate_equivalence"]["LEFT JOIN"] != True


# ==============================================================================
# TEST L: FULL JOIN Security Semantics False
# ==============================================================================
def test_l_full_join_security_semantics_false() -> None:
    layer = _load_approved_layer()
    relationships = {r["name"]: r for r in layer.get("relationships", [])}
    rel = relationships["branches_accounts"]

    assert rel["predicate_equivalence"]["FULL JOIN"] is False


# ==============================================================================
# TEST M: Measure Fanout Sensitivity
# ==============================================================================
def test_m_measure_fanout_sensitivity() -> None:
    layer = _load_approved_layer()
    measures = {m["name"]: m for m in layer.get("measures", [])}

    assert measures["Transaction Volume"]["fanout_sensitive"] is True
    assert measures["Total Balance"]["fanout_sensitive"] is True
    assert measures["Loan Exposure"]["fanout_sensitive"] is True
    assert measures["Customer Count"]["fanout_sensitive"] is True


# ==============================================================================
# TEST N: Context Completeness in Document Builder
# ==============================================================================
def test_n_context_completeness_in_document_builder() -> None:
    layer = _load_approved_layer()
    docs = SemanticDocumentBuilder().build(layer)

    rel_docs = [d for d in docs if d["object_type"] == "relationship"]
    assert len(rel_docs) == len(layer["relationships"])

    branch_rel_doc = next(d for d in rel_docs if d["payload"]["name"] == "branches_accounts")
    assert "cardinality: 1:N" in branch_rel_doc["text"]
    assert "security propagation: allowed" in branch_rel_doc["text"]


# ==============================================================================
# TEST O: Backward Compatibility
# ==============================================================================
def test_o_backward_compatibility() -> None:
    layer = _load_approved_layer()
    repo = MockSemanticRepository(layer)
    context = ContextRetrievalService(repo).build_llm_context(
        "Show transactions with accounts and customer names"
    )

    assert "SEMANTIC CONTEXT" in context
    assert "ENTITY: Customer -> customers" in context
    assert "TABLE: accounts" in context
    assert "COLUMNS: " in context
    assert "APPROVED RELATIONSHIPS:" in context
    assert "accounts.account_id -> transactions.account_id" in context
    assert "QUERY SCOPE:" in context


# ==============================================================================
# TEST P: Unknown Security Propagation Preserved
# ==============================================================================
def test_p_unknown_security_propagation_preserved() -> None:
    validator = SemanticLayerValidator()
    draft = _load_approved_layer()
    draft["relationships"].append({
        "name": "external_partner_rel",
        "from_table": "customers",
        "from_column": "customer_id",
        "to_table": "accounts",
        "to_column": "customer_id",
        "cardinality": "1:N",
        "relationship_type": "foreign_key",
        "security_propagation": "unknown",
    })
    # Valid security_propagation "unknown" should be accepted without invalid errors
    result = validator.validate(
        draft,
        {"tables": {"customers": {"columns": [{"name": "customer_id"}]}, "accounts": {"columns": [{"name": "customer_id"}]}}},
        draft["relationships"],
    )
    errors = [e for e in result["errors"] if e.get("code") == "invalid_security_propagation"]
    assert len(errors) == 0


# ==============================================================================
# TEST Q: Measure Source Integrity Rejected When Column Missing
# ==============================================================================
def test_q_measure_source_integrity_rejected_when_column_missing() -> None:
    validator = SemanticLayerValidator()
    schema = {"tables": {"orders": {"columns": [{"name": "id"}]}}}
    draft = {
        "metadata": {"semantic_layer_id": "SL-1", "revision_id": "REV-1", "status": "draft"},
        "entities": [{"name": "Order", "mapping": "orders"}],
        "relationships": [],
        "dimensions": [{"name": "ID", "mapping": "orders.id"}],
        "measures": [{"name": "Revenue", "mapping": "orders.non_existent_column"}],
        "business_rules": [],
    }
    result = validator.validate(draft, schema, [])
    codes = {e["code"] for e in result["errors"]}
    assert "unknown_measure_mapping" in codes


# ==============================================================================
# TEST R: Relationship Integrity Rejected When Table or Column Missing
# ==============================================================================
def test_r_relationship_integrity_rejected_when_target_missing() -> None:
    validator = SemanticLayerValidator()
    schema = {"tables": {"customers": {"columns": [{"name": "id"}]}}}
    invalid_rel = {
        "name": "invalid_rel",
        "from_table": "customers",
        "from_column": "id",
        "to_table": "missing_table",
        "to_column": "customer_id",
        "cardinality": "1:N",
        "relationship_type": "foreign_key",
    }
    draft = {
        "metadata": {"semantic_layer_id": "SL-1", "revision_id": "REV-1", "status": "draft"},
        "entities": [{"name": "Customer", "mapping": "customers"}],
        "relationships": [invalid_rel],
        "dimensions": [{"name": "ID", "mapping": "customers.id"}],
        "measures": [],
        "business_rules": [],
    }
    result = validator.validate(draft, schema, [invalid_rel])
    codes = {e["code"] for e in result["errors"]}
    assert "unknown_table" in codes
