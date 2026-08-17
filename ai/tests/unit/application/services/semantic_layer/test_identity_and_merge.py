from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import AffectedObject
from src.application.services.semantic_layer.merge.semantic_layer_merger_service import SemanticLayerMergeService
from src.application.services.semantic_layer.semantic_layer_identity_service import SemanticLayerIdentityService


def _layer():
    return {"metadata": {}, "entities": [{"name": "Customer", "object_id": "obj-entity-customer"}], "relationships": [], "measures": [], "dimensions": [], "business_rules": []}


def test_identity_is_deterministic_and_preserves_existing_ids():
    result = SemanticLayerIdentityService().assign_object_ids({"entities": [{"name": "Customer"}], "relationships": [], "measures": [], "dimensions": [], "business_rules": []})
    assert result["entities"][0]["object_id"] == "obj-entity-customer"


def test_incremental_merge_supports_add_update_and_delete():
    merger = SemanticLayerMergeService()
    base = _layer()
    update = merger.merge(base, {**_layer(), "entities": [{"name": "Customer Updated", "object_id": "obj-entity-customer"}]}, [AffectedObject("entities", action="update", id="obj-entity-customer").to_dict()])
    assert update["entities"][0]["name"] == "Customer Updated"
    added = merger.merge(base, {**_layer(), "entities": [{"name": "Account"}]}, [AffectedObject("entities", action="add", name="Account").to_dict()])
    assert added["entities"][-1]["object_id"] == "obj-entity-account"
    deleted = merger.merge(base, _layer(), [AffectedObject("entities", action="delete", id="obj-entity-customer").to_dict()])
    assert deleted["entities"] == []
