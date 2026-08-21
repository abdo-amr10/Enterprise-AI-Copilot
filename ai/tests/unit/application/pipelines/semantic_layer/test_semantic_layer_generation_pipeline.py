from unittest.mock import Mock

import pytest

from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    AffectedObject,
    SemanticLayerGenerationRequest,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.pipelines.semantic_layer.semantic_layer_generation_pipeline import (
    SemanticLayerGenerationPipeline,
)
from src.application.services.semantic_layer.merge.semantic_layer_merger_service import (
    SemanticLayerMergeService,
)
from src.application.services.semantic_layer.semantic_layer_identity_service import (
    SemanticLayerIdentityService,
)
from src.application.services.semantic_layer.semantic_layer_metadata_generator import (
    SemanticLayerMetadataService,
)


class _Ids:
    def __init__(self, initial=0):
        self.number = initial

    def generate_revision_id(self):
        self.number += 1
        return f"REV-{self.number:03d}"


def _layer(*entities):
    return {"metadata": {}, "entities": list(entities), "relationships": [],
            "measures": [], "dimensions": [], "business_rules": []}


def _pipeline(build_service, initial_revision=0):
    return SemanticLayerGenerationPipeline(
        build_service=build_service,
        merge_service=SemanticLayerMergeService(),
        metadata_service=SemanticLayerMetadataService(_Ids(initial_revision)),
        identity_service=SemanticLayerIdentityService(),
    )


def test_full_rebuild_assigns_metadata_and_object_ids():
    build_service = Mock()
    build_service.build.return_value = SemanticLayerBuildResponse(
        semantic_layer=_layer({"name": "Customer"})
    )
    result = _pipeline(build_service).run(
        SemanticLayerGenerationRequest("FullRebuild", {"schema": "file-1"}, "SL-001"),
        {"schema": {}, "relationships": []},
    )
    assert result["metadata"] == {
        "semantic_layer_id": "SL-001", "revision_id": "REV-001",
        "base_revision_id": None, "trigger_type": "FullRebuild",
        "status": "initial_draft", "validated": False, "human_review_required": True,
    }
    assert result["entities"][0]["object_id"].startswith("obj-")


def test_full_rebuild_rejects_baseline_and_incremental_requires_one():
    build_service = Mock()
    pipeline = _pipeline(build_service)
    full = SemanticLayerGenerationRequest("FullRebuild", {"schema": "file-1"}, "SL-001")
    with pytest.raises(ValueError, match="must not be provided"):
        pipeline.run(full, {"schema": {}, "relationships": []}, _layer())
    incremental = SemanticLayerGenerationRequest(
        "Incremental", {"schema": "file-1"}, "SL-001", "REV-001",
        (AffectedObject("entities", action="update", id="obj-1"),),
    )
    with pytest.raises(ValueError, match="requires an approved"):
        pipeline.run(incremental, {"schema": {}, "relationships": []})


def test_incremental_preserves_existing_id_and_metadata_lineage():
    build_service = Mock()
    build_service.build.return_value = SemanticLayerBuildResponse(
        semantic_layer=_layer({"name": "Customer v2", "object_id": "obj-1"})
    )
    request = SemanticLayerGenerationRequest(
        "Incremental", {"schema": "file-1"}, "SL-001", "REV-001",
        (AffectedObject("entities", action="update", id="obj-1"),),
    )
    result = _pipeline(build_service, initial_revision=1).run(
        request, {"schema": {}, "relationships": []},
        _layer({"name": "Customer", "object_id": "obj-1"}),
    )
    assert result["entities"][0]["object_id"] == "obj-1"
    assert result["metadata"]["revision_id"] == "REV-002"
    assert result["metadata"]["base_revision_id"] == "REV-001"
    assert result["metadata"]["trigger_type"] == "Incremental"
