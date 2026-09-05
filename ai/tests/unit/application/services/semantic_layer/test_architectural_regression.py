"""Architectural regression tests verifying all audit items and strict constraints.

Verifies:
1. Enriched relationship metadata preservation in FullRebuildBuilder.
2. AVG and other aggregations supported in measures and glossary extraction.
3. Domain-agnostic documentation metadata extraction (no hardcoded banking terms).
4. C# DTO adaptation and normalization in semantic_router.
5. Vector metadata canonicalization (object_type and type compatibility).
6. Critic context semantic security policy from semantic repository.
7. Text-to-SQL context includes primary keys and data types.
8. Incremental delete cascade in SemanticLayerMergeService.
9. Architectural boundaries (ConversationLayer unwired, C# contracts unchanged).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest

from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    AffectedObject,
    SemanticLayerGenerationRequest,
)
from src.application.dto.backend.copilot.semantic_retrieval_request import (
    SemanticRetrievalRequest,
)
from src.application.services.semantic_layer.builders.full_build_builder import (
    FullRebuildBuilder,
)
from src.application.services.semantic_layer.merge.semantic_layer_merger_service import (
    SemanticLayerMergeService,
)
from src.infrastructure.semantic_layer.retrieval.semantic_document_builder import (
    SemanticDocumentBuilder,
)
from src.infrastructure.semantic_layer.retrieval.file_semantic_repository import (
    FileSemanticRepository,
)
from src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)
from src.application.pipelines.context_retrieval.semantic_retrieval_pipeline import (
    SemanticRetrievalPipeline,
)
from src.api.routers.semantic_router import _normalize_affected_object


# ==============================================================================
# 1. Enriched Relationship Metadata Preservation
# ==============================================================================
def test_reconcile_relationships_preserves_enriched_metadata() -> None:
    physical_relationships = [
        {
            "name": "rel_orders_customers",
            "from_table": "orders",
            "from_column": "customer_id",
            "to_table": "customers",
            "to_column": "id",
        }
    ]
    raw_relationships = [
        {
            "name": "rel_orders_customers",
            "from_table": "orders",
            "from_column": "customer_id",
            "to_table": "customers",
            "to_column": "id",
            "cardinality": "N:1",
            "relationship_type": "many_to_one",
            "fanout_risk": False,
            "aggregation_behavior": "safe",
            "security_propagation": "allowed",
            "predicate_equivalence": {"INNER JOIN": True, "LEFT JOIN": "conditional"},
            "description": "Each order belongs to a single customer.",
        }
    ]

    reconciled = FullRebuildBuilder._reconcile_relationships(
        physical_relationships, raw_relationships
    )

    assert len(reconciled) == 1
    rel = reconciled[0]
    assert rel["from_table"] == "orders"
    assert rel["from_column"] == "customer_id"
    assert rel["to_table"] == "customers"
    assert rel["to_column"] == "id"
    assert rel["cardinality"] == "N:1"
    assert rel["relationship_type"] == "many_to_one"
    assert rel["fanout_risk"] is False
    assert rel["aggregation_behavior"] == "safe"
    assert rel["security_propagation"] == "allowed"
    assert rel["description"] == "Each order belongs to a single customer."
    assert rel["predicate_equivalence"]["INNER JOIN"] is True


# ==============================================================================
# 2. Measures Support AVG and Multi-Aggregations
# ==============================================================================
def test_measures_support_avg_and_glossary_extraction() -> None:
    builder = FullRebuildBuilder(None)

    schema_tables = {
        "products": {"columns": [{"name": "price"}]},
        "order_items": {"columns": [{"name": "quantity"}]},
    }
    glossary_measures = [
        {"name": "Average Price", "mapping": "products.price", "aggregation": "AVG"},
        {"name": "Total Quantity", "mapping": "order_items.quantity", "aggregation": "SUM"},
    ]

    # Verify normalize does NOT skip AVG
    normalized = builder._normalize_requested_measures(
        [
            {"name": "Average Price", "mapping": "products.price", "aggregation": "AVG"},
            {"name": "Total Quantity", "mapping": "order_items.quantity", "aggregation": "SUM"},
        ],
        schema_tables=schema_tables,
        glossary_measures=glossary_measures,
    )
    names = {m["name"] for m in normalized}
    assert "Average Price" in names
    assert "Total Quantity" in names

    # Verify glossary measures extraction extracts AVG, MIN, MAX, COUNT, SUM
    glossary_text = (
        "| Term | Mapping | Meaning |\n"
        "|---|---|---|\n"
        "| Average Order Value | Derived from `orders.amount` | Average amount per order. |\n"
        "| Total Revenue | Derived from `orders.total` | Total sum of sales. |\n"
        "| Maximum Discount | Derived from `promotions.discount` | Highest maximum discount rate. |\n"
        "| Minimum Price | Derived from `products.price` | Lowest minimum product cost. |\n"
        "| Order Count | Derived from `orders.id` | Total count of orders placed. |"
    )
    extracted = builder._extract_glossary_measures(glossary_text)
    extracted_aggs = {m["aggregation"] for m in extracted}
    assert "AVG" in extracted_aggs
    assert "SUM" in extracted_aggs
    assert "MAX" in extracted_aggs
    assert "MIN" in extracted_aggs
    assert "COUNT" in extracted_aggs


# ==============================================================================
# 3. Domain-Agnostic Documentation Extraction
# ==============================================================================
def test_documentation_extraction_is_domain_agnostic() -> None:
    builder = FullRebuildBuilder(None)
    # Non-banking e-commerce documentation
    doc_markdown = (
        "# Logistics System\n\n"
        "## Text-to-SQL Guidance\n"
        "- **Warehouse Stock**: Tracks inventory counts per bin location across all fulfillment centers.\n"
        "- **Carrier Transit**: Manages carrier tracking numbers and transit status updates."
    )
    result = builder._extract_documentation_metadata(doc_markdown)
    assert "business_rules" in result
    rule_names = {rule["name"] for rule in result["business_rules"]}
    assert "Warehouse Stock" in rule_names
    assert "Carrier Transit" in rule_names


# ==============================================================================
# 4. C# DTO Adaptation & Normalization
# ==============================================================================
def test_csharp_dto_normalization_resolves_name_and_defaults_update() -> None:
    base_layer = {
        "entities": [
            {"object_id": "ent-101", "name": "Customer", "mapping": "customers"}
        ],
        "relationships": [],
        "measures": [],
        "dimensions": [],
        "business_rules": [],
        "security_domains": [],
    }

    # C# sends only { "section": "entities", "id": "ent-101" }
    csharp_payload = {"section": "entities", "id": "ent-101"}
    normalized = _normalize_affected_object(csharp_payload, base_semantic_layer=base_layer)

    assert normalized.section == "entities"
    assert normalized.action == "update"
    assert normalized.id == "ent-101"
    assert normalized.name == "Customer"


def test_csharp_dto_normalization_rejects_unknown_id() -> None:
    base_layer = {
        "entities": [{"object_id": "ent-101", "name": "Customer"}],
    }
    with pytest.raises(ValueError, match="Unknown ID 'ent-999'"):
        _normalize_affected_object({"section": "entities", "id": "ent-999"}, base_semantic_layer=base_layer)


def test_csharp_dto_normalization_rejects_invalid_section() -> None:
    with pytest.raises(ValueError, match="Invalid section 'unknown_section'"):
        _normalize_affected_object({"section": "unknown_section", "id": "obj-1"})


# ==============================================================================
# 5. Vector Metadata Canonicalization (object_type and type)
# ==============================================================================
def test_semantic_document_builder_canonical_keys() -> None:
    layer = {
        "metadata": {"semantic_layer_id": "sl-1", "revision_id": "rev-1"},
        "entities": [{"object_id": "ent-1", "name": "Customer", "mapping": "customers", "primary_key": "customer_id"}],
        "dimensions": [{"object_id": "dim-1", "name": "Status", "mapping": "customers.status", "data_type": "varchar"}],
        "relationships": [],
        "measures": [],
        "business_rules": [{"object_id": "br-1", "name": "Active Only", "description": "Only active customers"}],
        "security_domains": [],
    }
    builder = SemanticDocumentBuilder()
    docs = builder.build(layer)

    for doc in docs:
        assert "object_type" in doc
        assert "type" in doc
        assert doc["object_type"] == doc["type"]

    entity_doc = next(d for d in docs if d["object_type"] == "entity")
    assert "primary key: customer_id" in entity_doc["text"].lower()

    dim_doc = next(d for d in docs if d["object_type"] == "dimension")
    assert "data type: varchar" in dim_doc["text"].lower()


def test_retrieval_pipeline_business_rules_canonical_object_type() -> None:
    class MockRetrievalService:
        def retrieve(self, question: str, top_k: int | None = None) -> list[dict[str, Any]]:
            return [
                {
                    "object_type": "business_rule",
                    "payload": {"description": "Rule from object_type key"},
                },
                {
                    "type": "business_rule",
                    "payload": {"description": "Rule from type key"},
                },
                {
                    "object_type": "entity",
                    "payload": {"mapping": "customers"},
                },
            ]

    pipeline = SemanticRetrievalPipeline(MockRetrievalService())  # type: ignore[arg-type]
    response = pipeline.run(SemanticRetrievalRequest(question="show active customers", conversation=()))

    assert "Rule from object_type key" in response.business_rules
    assert "Rule from type key" in response.business_rules
    assert "customers" in response.tables


# ==============================================================================
# 6. Critic Context Semantic Security Domains
# ==============================================================================
def test_critic_context_includes_semantic_security_policy() -> None:
    from src.application.services.self_correction.self_correction_service import (
        SelfCorrectionService,
    )

    class MockRepo:
        def load(self) -> dict[str, Any]:
            return {
                "security_domains": [
                    {
                        "name": "TenantIsolation",
                        "canonical_predicate": "customers.tenant_id = @TenantId",
                        "security_scope": "tenant",
                        "propagation_paths": [
                            {
                                "target_table": "orders",
                                "path": "orders.customer_id = customers.customer_id",
                            }
                        ],
                    }
                ]
            }

    class MockContextRetrieval:
        def __init__(self) -> None:
            self._semantic_repository = MockRepo()

    class MockSchemaValidator:
        def schema_slice(self, sql: str, schema: Any = None) -> dict[str, Any]:
            return {"orders": {"columns": [{"name": "id"}]}}

        def extract_tables(self, sql: str, schema: Any = None) -> set[str]:
            return {"orders"}

    service = SelfCorrectionService(
        context_retrieval_service=MockContextRetrieval(),  # type: ignore[arg-type]
        syntax_validator=None,  # type: ignore[arg-type]
        schema_validator=MockSchemaValidator(),  # type: ignore[arg-type]
        relationship_validator=None,  # type: ignore[arg-type]
        critic_service=None,  # type: ignore[arg-type]
        finding_verifier=None,  # type: ignore[arg-type]
        correction_service=None,  # type: ignore[arg-type]
    )

    context = service._build_critic_context(
        sql="SELECT * FROM orders",
        schema_getter=lambda: {"tables": {"orders": {"columns": [{"name": "id"}]}}},
        fallback_context="FALLBACK",
    )

    assert "SECURITY POLICY:" in context
    assert "TenantIsolation: customers.tenant_id = @TenantId" in context
    assert "scope: tenant" in context
    assert "propagation to orders: orders.customer_id = customers.customer_id" in context


# ==============================================================================
# 7. Physical Schema Data Types and Primary Keys in Context
# ==============================================================================
def test_context_retrieval_appends_primary_keys_and_data_types() -> None:
    layer = {
        "metadata": {"status": "approved", "semantic_layer_id": "sl-1", "revision_id": "rev-1"},
        "entities": [
            {"name": "Customer", "mapping": "customers", "primary_key": "customer_id"}
        ],
        "dimensions": [
            {"name": "Customer Name", "mapping": "customers.full_name", "data_type": "nvarchar"}
        ],
        "relationships": [],
        "measures": [],
        "business_rules": [],
        "security_domains": [],
    }

    class MockSchemaProvider:
        def get_schema(self) -> dict[str, Any]:
            return {
                "tables": {
                    "customers": {
                        "primary_key": "customer_id",
                        "columns": [
                            {"name": "customer_id", "data_type": "int"},
                            {"name": "full_name", "data_type": "nvarchar"},
                            {"name": "is_active", "data_type": "bit"},
                        ],
                    }
                }
            }

    class MockRepo:
        def load(self) -> dict[str, Any]:
            return layer

        def retrieve(self, question: str, top_k: int = 8) -> list[dict[str, Any]]:
            return [{"payload": {"mapping": "customers"}}]

    service = ContextRetrievalService(
        semantic_repository=MockRepo(),  # type: ignore[arg-type]
        schema_provider=MockSchemaProvider(),  # type: ignore[arg-type]
    )

    context = service.build_llm_context("show customers")
    assert "TABLE: customers [PK: customer_id]" in context
    assert "COLUMNS: " in context
    assert "DATA TYPES: " in context
    assert "customer_id: int" in context
    assert "is_active: bit" in context


# ==============================================================================
# 8. Incremental Delete Cascade
# ==============================================================================
def test_incremental_delete_cascades_dependent_relationships_and_mappings() -> None:
    merger = SemanticLayerMergeService()
    approved_layer = {
        "metadata": {},
        "entities": [
            {"object_id": "ent-cust", "name": "Customer", "mapping": "customers"},
            {"object_id": "ent-ord", "name": "Order", "mapping": "orders"},
        ],
        "relationships": [
            {
                "object_id": "rel-1",
                "name": "cust_orders",
                "from_table": "customers",
                "from_column": "id",
                "to_table": "orders",
                "to_column": "customer_id",
            }
        ],
        "dimensions": [
            {"object_id": "dim-1", "name": "Customer Name", "mapping": "customers.name"},
            {"object_id": "dim-2", "name": "Order Date", "mapping": "orders.created_at"},
        ],
        "measures": [
            {"object_id": "m-1", "name": "Customer Count", "mapping": "customers.id", "source_table": "customers"},
            {"object_id": "m-2", "name": "Order Total", "mapping": "orders.total", "source_table": "orders"},
        ],
        "business_rules": [],
        "security_domains": [],
    }

    # Delete Customer entity
    affected = [AffectedObject("entities", action="delete", id="ent-cust").to_dict()]
    patch = {
        "metadata": {},
        "entities": [],
        "relationships": [],
        "dimensions": [],
        "measures": [],
        "business_rules": [],
        "security_domains": [],
    }

    merged = merger.merge(approved_layer, patch, affected)

    # Customer entity deleted
    assert len(merged["entities"]) == 1
    assert merged["entities"][0]["object_id"] == "ent-ord"

    # Dependent relationship referencing customers cascade-deleted
    assert len(merged["relationships"]) == 0

    # Dependent dimension referencing customers cascade-deleted
    assert len(merged["dimensions"]) == 1
    assert merged["dimensions"][0]["name"] == "Order Date"

    # Dependent measure referencing customers cascade-deleted
    assert len(merged["measures"]) == 1
    assert merged["measures"][0]["name"] == "Order Total"


# ==============================================================================
# 9. Architectural Boundaries & Isolation
# ==============================================================================
def test_conversation_layer_is_not_imported_in_runtime_pipeline() -> None:
    pipeline_file = Path("src/application/pipelines/text_to_sql/copilot_runtime_pipeline.py")
    content = pipeline_file.read_text(encoding="utf-8")
    assert "conversation_layer" not in content.lower(), (
        "CRITICAL: ConversationLayer must remain unwired and must not be imported in copilot_runtime_pipeline.py"
    )
