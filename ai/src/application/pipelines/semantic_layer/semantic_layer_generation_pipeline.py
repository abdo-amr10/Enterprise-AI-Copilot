"""Orchestrates Semantic Layer generation: build, merge, and identity assignment."""

from typing import Any

from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.services.semantic_layer.semantic_layer_build_service import (
    SemanticLayerBuildService,
)
from src.application.services.semantic_layer.merge.semantic_layer_merger_service import (
    SemanticLayerMergeService,
)
from src.application.services.semantic_layer.semantic_layer_metadata_generator import (
    SemanticLayerMetadataService,
)
from src.application.services.semantic_layer.semantic_layer_identity_service import (
    SemanticLayerIdentityService,
)


class SemanticLayerGenerationPipeline:
    """Generate a new Semantic Layer revision.

    Identity ownership: semantic_layer_id and revision_id are assigned
    here, right after build/merge, by delegating to
    SemanticLayerMetadataService (the single authoritative source for
    those two IDs). object_id values for individual semantic objects
    are then filled in by SemanticLayerIdentityService. `version` is
    deliberately NOT assigned in this pipeline -- it is only needed
    once a revision is persisted, which happens later, outside of
    Generation/Validation/Review.
    """

    def __init__(
        self,
        build_service: SemanticLayerBuildService,
        merge_service: SemanticLayerMergeService,
        metadata_service: SemanticLayerMetadataService,
        identity_service: SemanticLayerIdentityService,
    ) -> None:

        self._build_service = build_service
        self._merge_service = merge_service
        self._metadata_service = metadata_service
        self._identity_service = identity_service

    def run(
        self,
        request: SemanticLayerGenerationRequest,
        sources: dict[str, Any],
        base_semantic_layer: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        build_result: SemanticLayerBuildResponse = self._build_service.build(
            request=request,
            sources=sources,
            base_semantic_layer=base_semantic_layer,
        )

        if request.trigger_type == "FullRebuild":

            draft = self._metadata_service.initialize(
                build_result.semantic_layer
            )

        else:

            if base_semantic_layer is None:
                raise ValueError(
                    "Incremental generation requires "
                    "an approved base Semantic Layer."
                )

            merged = self._merge_service.merge(
                approved_layer=base_semantic_layer,
                incremental_layer=build_result.semantic_layer,
                affected_objects=[
                    obj.to_dict() for obj in request.affected_objects
                ],
            )

            draft = self._metadata_service.create_revision(
                semantic_layer=merged,
                semantic_layer_id=request.semantic_layer_id,
                base_revision_id=request.base_revision_id,
            )

        return self._identity_service.assign_object_ids(draft)
