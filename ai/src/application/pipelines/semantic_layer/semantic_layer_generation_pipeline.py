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
    """Generate an initial Semantic Layer draft.

    Generation builds, merges when incremental, and assigns metadata and
    object identities. Validation, persistence, approval, embedding, and
    indexing are intentionally separate stages.
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

        if not request.revision_id:
            raise ValueError(
                "revision_id must be assigned by Backend before AI generation."
            )

        if request.trigger_type == "FullRebuild":
            if base_semantic_layer is not None:
                raise ValueError(
                    "base_semantic_layer must not be provided for FullRebuild."
                )
            build_result: SemanticLayerBuildResponse = self._build_service.build(
                request=request,
                sources=sources,
            )
            draft = self._metadata_service.initialize(
                semantic_layer=build_result.semantic_layer,
                semantic_layer_id=request.semantic_layer_id,
                revision_id=request.revision_id,
            )
        elif request.trigger_type == "Incremental":
            if base_semantic_layer is None:
                raise ValueError(
                    "Incremental generation requires an approved base_semantic_layer."
                )
            if not request.base_revision_id:
                raise ValueError(
                    "base_revision_id is required for Incremental generation."
                )
            if not request.affected_objects:
                raise ValueError(
                    "affected_objects is required for Incremental generation."
                )
            build_result = self._build_service.build(
                request=request,
                sources=sources,
                base_semantic_layer=base_semantic_layer,
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
                revision_id=request.revision_id,
                base_revision_id=request.base_revision_id,
            )
        else:
            raise ValueError(f"Unsupported trigger_type: {request.trigger_type}")

        return self._identity_service.assign_object_ids(draft)
