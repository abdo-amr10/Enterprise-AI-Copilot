from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import AffectedObject
from src.application.services.semantic_layer.merge.semantic_layer_merger_service import SemanticLayerMergeService
from src.application.services.semantic_layer.semantic_layer_identity_service import SemanticLayerIdentityService


def _layer():
    return {"metadata": {}, "entities": [{"name": "Customer", "object_id": "obj-entity-customer"}], "relationships": [], "measures": [], "dimensions": [], "business_rules": []}


def test_identity_assigns_uuid_ids_and_preserves_existing_ids():
    result = SemanticLayerIdentityService().assign_object_ids({"entities": [{"name": "Customer"}], "relationships": [], "measures": [], "dimensions": [], "business_rules": []})
    assert result["entities"][0]["object_id"].startswith("obj-")
    existing = SemanticLayerIdentityService().assign_object_ids(_layer())
    assert existing["entities"][0]["object_id"] == "obj-entity-customer"


def test_incremental_merge_supports_add_update_and_delete():
    merger = SemanticLayerMergeService()
    base = _layer()
    update = merger.merge(base, {**_layer(), "entities": [{"name": "Customer Updated", "object_id": "obj-entity-customer"}]}, [AffectedObject("entities", action="update", id="obj-entity-customer").to_dict()])
    assert update["entities"][0]["name"] == "Customer Updated"
    added = merger.merge(base, {**_layer(), "entities": [{"name": "Account"}]}, [AffectedObject("entities", action="add", name="Account").to_dict()])
    assert "object_id" not in added["entities"][-1]
    added = SemanticLayerIdentityService().assign_object_ids(added)
    assert added["entities"][-1]["object_id"].startswith("obj-")
    deleted = merger.merge(base, _layer(), [AffectedObject("entities", action="delete", id="obj-entity-customer").to_dict()])
    assert deleted["entities"] == []


def test_incremental_merge_rejects_unauthorized_changes_and_preserves_unaffected_items():
    merger = SemanticLayerMergeService()
    base = {
        "metadata": {},
        "entities": [
            {"name": "Customer", "object_id": "obj-customer"},
            {"name": "Orders", "object_id": "obj-orders"},
            {"name": "Branch", "object_id": "obj-branch"},
        ],
        "relationships": [], "measures": [], "dimensions": [], "business_rules": [],
    }
    affected = [AffectedObject("entities", action="update", id="obj-customer").to_dict()]
    patch = {"metadata": {}, "entities": [
        {"name": "Customer updated", "object_id": "obj-customer"}
    ], "relationships": [], "measures": [], "dimensions": [], "business_rules": []}
    merged = merger.merge(base, patch, affected)
    assert merged["entities"][1:] == base["entities"][1:]

    unauthorized_patch = {**patch, "entities": patch["entities"] + [{"name": "Branch"}]}
    import pytest
    with pytest.raises(ValueError, match="outside the affected_objects scope"):
        merger.merge(base, unauthorized_patch, affected)


def test_merge_rebuilds_indexes_after_deletion_before_update():
    merger = SemanticLayerMergeService()
    base = {
        "metadata": {},
        "entities": [
            {"name": "Customer", "object_id": "obj-customer"},
            {"name": "Orders", "object_id": "obj-orders"},
        ],
        "relationships": [], "measures": [], "dimensions": [], "business_rules": [],
    }
    result = merger.merge(
        base,
        {"metadata": {}, "entities": [{"name": "Orders v2", "object_id": "obj-orders"}],
         "relationships": [], "measures": [], "dimensions": [], "business_rules": []},
        [
            AffectedObject("entities", action="delete", id="obj-customer").to_dict(),
            AffectedObject("entities", action="update", id="obj-orders").to_dict(),
        ],
    )
    assert result["entities"] == [{"name": "Orders v2", "object_id": "obj-orders"}]
