from unittest.mock import Mock

from src.application.pipelines.semantic_layer.semantic_layer_validation_pipeline import (
    SemanticLayerValidationPipeline,
)
from src.application.services.semantic_layer.validation.semantic_layer_auto_fixer import (
    SemanticLayerAutoFixer,
)
from src.application.services.semantic_layer.validation.semantic_layer_validator import (
    SemanticLayerValidator,
)


RELATIONSHIPS = [{
    "name": "Orders_Customers", "from_table": "orders", "from_column": "customer_id",
    "to_table": "customers", "to_column": "id", "cardinality": "many_to_one",
    "relationship_type": "foreign_key",
}]
SCHEMA = {
    "tables": {
        "customers": {"columns": [{"name": "id"}, {"name": "name"}]},
        "orders": {"columns": [{"name": "customer_id"}, {"name": "amount"}]},
    }
}


def _draft(trigger_type="FullRebuild"):
    return {
        "metadata": {
            "semantic_layer_id": "SL-001", "revision_id": "REV-001",
            "status": "initial_draft", "trigger_type": trigger_type,
            "validated": False, "human_review_required": True,
        },
        "entities": [{"name": "Customer", "mapping": "customers"}],
        "relationships": [], "measures": [], "dimensions": [],
        "business_rules": [], "validation_issues": [],
    }


def test_full_rebuild_requires_authoritative_relationships_to_be_represented():
    result = SemanticLayerValidator().validate(_draft(), SCHEMA, RELATIONSHIPS)
    assert result["status"] == "failed"
    assert any(error["code"] == "missing_relationship" for error in result["errors"])


def test_incremental_validates_merged_content_without_missing_source_relationship_rule():
    result = SemanticLayerValidator().validate(
        _draft("Incremental"), SCHEMA, RELATIONSHIPS
    )
    assert result["status"] == "passed"


def test_full_rebuild_rejects_missing_source_column_dimensions():
    draft = _draft()
    draft["relationships"] = RELATIONSHIPS
    draft["dimensions"] = [
        {"name": "Customer ID", "mapping": "customers.id"},
        {"name": "Customer Name", "mapping": "customers.name"},
        {"name": "Order Customer ID", "mapping": "orders.customer_id"},
    ]

    result = SemanticLayerValidator().validate(
        draft, SCHEMA, RELATIONSHIPS, has_semantic_context=True
    )

    assert result["status"] == "failed"
    assert any(
        error["code"] == "missing_dimension_mapping"
        and "orders.amount" in error["message"]
        for error in result["errors"]
    )


def test_full_rebuild_rejects_missing_entities_and_empty_semantic_sections():
    draft = _draft()
    draft["relationships"] = RELATIONSHIPS
    draft["dimensions"] = [
        {"name": "Customer ID", "mapping": "customers.id"},
        {"name": "Customer Name", "mapping": "customers.name"},
        {"name": "Order Customer ID", "mapping": "orders.customer_id"},
        {"name": "Order Amount", "mapping": "orders.amount"},
    ]

    result = SemanticLayerValidator().validate(
        draft, SCHEMA, RELATIONSHIPS, has_semantic_context=True
    )

    codes = {error["code"] for error in result["errors"]}
    assert {"missing_entity_mapping", "missing_measures", "missing_business_rules"} <= codes


def test_schema_only_full_rebuild_allows_empty_enrichment_sections():
    draft = _draft()
    draft["entities"].append({"name": "Order", "mapping": "orders"})
    draft["relationships"] = RELATIONSHIPS
    draft["dimensions"] = [
        {"name": "Customer ID", "mapping": "customers.id"},
        {"name": "Customer Name", "mapping": "customers.name"},
        {"name": "Order Customer ID", "mapping": "orders.customer_id"},
        {"name": "Order Amount", "mapping": "orders.amount"},
    ]

    result = SemanticLayerValidator().validate(draft, SCHEMA, RELATIONSHIPS)

    assert result["status"] == "passed"


def test_relationship_and_mapping_errors_are_detected():
    draft = _draft("Incremental")
    draft["relationships"] = [{**RELATIONSHIPS[0], "to_column": "missing"}]
    draft["measures"] = [{"name": "Revenue", "mapping": "orders.not_a_column"}]
    result = SemanticLayerValidator().validate(draft, SCHEMA, RELATIONSHIPS)
    codes = {error["code"] for error in result["errors"]}
    assert "relationship_mismatch" in codes
    assert "unknown_measure_mapping" in codes


def test_validation_pipeline_marks_a_successful_draft_validated():
    draft = _draft("Incremental")
    pipeline = SemanticLayerValidationPipeline(
        validator=SemanticLayerValidator(), auto_fixer=Mock(), max_fix_attempts=0
    )
    final_draft, validation = pipeline.run(draft, SCHEMA, RELATIONSHIPS)
    assert validation["status"] == "passed"
    assert final_draft["metadata"]["validated"] is True
    assert final_draft["metadata"]["status"] == "validated"
    assert final_draft["metadata"]["human_review_required"] is True


def test_auto_fixer_preserves_generation_metadata_and_object_ids():
    original = _draft("Incremental")
    original["metadata"]["base_revision_id"] = "REV-000"
    original["entities"][0]["object_id"] = "obj-customer"
    corrected = {
        **_draft("FullRebuild"),
        "entities": [{"name": "Customer", "mapping": "customers"}],
    }
    result = SemanticLayerAutoFixer._preserve_identity(original, corrected)
    assert result["metadata"]["semantic_layer_id"] == "SL-001"
    assert result["metadata"]["revision_id"] == "REV-001"
    assert result["metadata"]["base_revision_id"] == "REV-000"
    assert result["metadata"]["trigger_type"] == "Incremental"
    assert result["entities"][0]["object_id"] == "obj-customer"
