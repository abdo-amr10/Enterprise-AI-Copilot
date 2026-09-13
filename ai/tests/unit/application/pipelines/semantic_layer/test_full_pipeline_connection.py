"""End-to-end pipeline connectivity test verifying all stages from request to response contract."""

import json
from unittest.mock import Mock

from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.pipelines.semantic_layer.semantic_layer_generation_pipeline import (
    SemanticLayerGenerationPipeline,
)
from src.application.services.semantic_layer.builders.full_build_builder import (
    FullRebuildBuilder,
)
from src.application.services.semantic_layer.builders.incremental_builder import (
    IncrementalBuilder,
)
from src.application.services.semantic_layer.merge.semantic_layer_merger_service import (
    SemanticLayerMergeService,
)
from src.application.services.semantic_layer.relationships.relationship_service import (
    RelationshipProcessingEngine,
)
from src.application.services.semantic_layer.semantic_layer_build_service import (
    SemanticLayerBuildService,
)
from src.application.services.semantic_layer.semantic_layer_identity_service import (
    SemanticLayerIdentityService,
)
from src.application.services.semantic_layer.semantic_layer_metadata_generator import (
    SemanticLayerMetadataService,
)
from src.application.services.semantic_layer.strategy.full_rebuild_strategy import (
    FullRebuildStrategy,
)
from src.application.services.semantic_layer.strategy.incremental_build_strategy import (
    IncrementalBuildStrategy,
)


def test_full_pipeline_connection_end_to_end():
    """Verify that every stage of the generation pipeline connects without error."""

    # 1. Mock LLM client simulating concise responses from the decomposed sub-prompts
    llm_client = Mock()

    def llm_side_effect(gen_request):
        prompt = gen_request.prompt
        if "ENTITY_SEMANTIC_PROMPT" in prompt or "BUSINESS GLOSSARY:" in prompt:
            return GenerationResponse(
                text=json.dumps({
                    "entities": [
                        {
                            "mapping": "customers",
                            "name": "Customer",
                            "description": "Registered retail client accounts.",
                            "synonyms": ["client", "buyer"],
                        },
                        {
                            "mapping": "orders",
                            "name": "Order",
                            "description": "Sales order transactions placed by customers.",
                            "synonyms": ["purchase", "invoice"],
                        },
                    ]
                })
            )
        elif "RELATIONSHIP_SEMANTIC_PROMPT" in prompt:
            return GenerationResponse(
                text=json.dumps({
                    "relationships": [
                        {
                            "from_table": "orders",
                            "to_table": "customers",
                            "from_column": "customer_id",
                            "to_column": "customer_id",
                            "description": "Connects each order to its placing customer.",
                            "join_intent": "Customer profile lookup",
                        }
                    ]
                })
            )
        elif "GLOSSARY_SEMANTIC_PROMPT" in prompt:
            return GenerationResponse(
                text=json.dumps({
                    "measures": [
                        {
                            "name": "Total Order Value",
                            "mapping": "orders.total_amount",
                            "aggregation": "SUM",
                            "description": "Gross total amount of orders placed.",
                        }
                    ],
                    "business_rules": [],
                })
            )
        return GenerationResponse(text="{}")

    llm_client.generate.side_effect = llm_side_effect

    # 2. Assemble complete Clean Architecture dependencies
    full_rebuild_builder = FullRebuildBuilder(llm_client=llm_client)
    full_rebuild_strategy = FullRebuildStrategy(
        builder=full_rebuild_builder,
        relationship_engine=RelationshipProcessingEngine(),
    )
    incremental_builder = IncrementalBuilder(llm_client=llm_client)
    incremental_strategy = IncrementalBuildStrategy(builder=incremental_builder)
    build_service = SemanticLayerBuildService(
        full_rebuild_strategy=full_rebuild_strategy,
        incremental_strategy=incremental_strategy,
    )
    pipeline = SemanticLayerGenerationPipeline(
        build_service=build_service,
        merge_service=SemanticLayerMergeService(),
        metadata_service=SemanticLayerMetadataService(),
        identity_service=SemanticLayerIdentityService(),
    )

    # 3. Simulate realistic multi-table schema with foreign keys and RLS policy
    sources = {
        "schema": {
            "version": "1.0",
            "database": "TestEnterpriseDb",
            "tables": {
                "customers": {
                    "columns": [
                        {"name": "customer_id", "type": "int", "primary_key": True},
                        {"name": "store_id", "type": "int"},
                        {"name": "email", "type": "varchar"},
                    ]
                },
                "orders": {
                    "columns": [
                        {"name": "order_id", "type": "int", "primary_key": True},
                        {"name": "customer_id", "type": "int"},
                        {"name": "store_id", "type": "int"},
                        {"name": "total_amount", "type": "decimal"},
                    ],
                },
            },
        },
        "relationships": [
            {
                "name": "fk_orders_customers",
                "from_table": "orders",
                "from_column": "customer_id",
                "to_table": "customers",
                "to_column": "customer_id",
            }
        ],
        "documentation": "Orders belong to customers. Restrict queries by store_id.",
        "business_glossary": (
            "| Term | Mapping | Meaning |\n"
            "|---|---|---|\n"
            "| Total Revenue | Derived from `orders.total_amount` | Total sum of sales. |\n"
        ),
        "rls_policy": {
            "enabled": True,
            "userValueField": "StoreId",
            "scopeParameter": "@UserStoreId",
            "rules": [
                {"table": "customers", "scopeColumn": "store_id", "type": "direct"},
                {"table": "orders", "scopeColumn": "store_id", "type": "direct"},
            ],
        },
    }

    generation_request = SemanticLayerGenerationRequest(
        trigger_type="FullRebuild",
        semantic_layer_id="SL-TEST-001",
        source_file_ids={"schema": "file-schema-1"},
    )

    # 4. Execute the pipeline
    draft = pipeline.run(request=generation_request, sources=sources)

    # 5. Verify every structural contract and connection
    assert isinstance(draft, dict)

    # Metadata checks
    metadata = draft["metadata"]
    assert metadata["semantic_layer_id"] == "SL-TEST-001"
    assert metadata["trigger_type"] == "FullRebuild"
    assert metadata["status"] == "initial_draft"
    assert metadata["validated"] is False
    assert metadata["human_review_required"] is True

    # Entities checks
    entities = draft["entities"]
    assert len(entities) == 2
    customer_ent = next(e for e in entities if e["mapping"] == "customers")
    order_ent = next(e for e in entities if e["mapping"] == "orders")
    assert customer_ent["object_id"].startswith("obj-")
    assert customer_ent["natural_grain"] == "customer_id"
    assert customer_ent["security_scope"] == "store"
    assert order_ent["object_id"].startswith("obj-")
    assert order_ent["natural_grain"] == "order_id"
    assert order_ent["security_scope"] == "store"

    # Relationships checks (verified by RelationshipProcessingEngine + LLM enricher)
    relationships = draft["relationships"]
    assert len(relationships) >= 1
    rel = next(r for r in relationships if r["from_table"] == "orders" and r["to_table"] == "customers")
    assert rel["object_id"].startswith("obj-")
    assert rel["from_column"] == "customer_id"
    assert rel["to_column"] == "customer_id"
    assert "description" in rel
    assert rel["cardinality"] in ("N:1", "1:N", "1:1", "many_to_one")

    # Dimensions checks (governed deterministically from physical schema)
    dimensions = draft["dimensions"]
    assert len(dimensions) == 7  # 3 cols from customers + 4 cols from orders
    email_dim = next(d for d in dimensions if d["mapping"] == "customers.email")
    assert email_dim["object_id"].startswith("obj-")
    assert email_dim["is_pii"] is True
    assert email_dim["sensitivity"] == "confidential"

    # Measures checks (from glossary and normalization)
    measures = draft["measures"]
    assert len(measures) >= 1
    measure_names = {m["name"] for m in measures}
    assert "Total Revenue" in measure_names or "Total Order Value" in measure_names

    # Security domains checks (adapted from RLS policy)
    security_domains = draft["security_domains"]
    assert len(security_domains) >= 1
    store_domain = next(d for d in security_domains if d.get("name") == "store" or d.get("security_scope") == "store")
    assert store_domain["security_parameter"] == "@UserStoreId"
    assert "store_id" in store_domain["canonical_root"]

    # Simulate router output normalization for both C# Backend and internal consumers
    router_response = dict(draft)
    if "business_rules" in router_response:
        rules = router_response.get("business_rules") or []
        router_response["businessRules"] = rules
        router_response["business_rules"] = rules
    if "validation_issues" in router_response:
        issues = router_response.get("validation_issues") or []
        router_response["validationIssues"] = issues
        router_response["validation_issues"] = issues
    if "security_domains" in router_response:
        domains = router_response.get("security_domains") or []
        router_response["securityDomains"] = domains
        router_response["security_domains"] = domains

    # Verify C# Backend JSON properties are present
    assert "entities" in router_response
    assert "relationships" in router_response
    assert "measures" in router_response
    assert "dimensions" in router_response
    assert "businessRules" in router_response
    assert "business_rules" in router_response
    assert "securityDomains" in router_response
    assert "security_domains" in router_response
    assert "validationIssues" in router_response
    assert "validation_issues" in router_response
    assert "metadata" in router_response
