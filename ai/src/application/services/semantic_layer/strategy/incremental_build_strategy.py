from typing import Any

from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.services.semantic_layer.builders.incremental_builder import (
    IncrementalBuilder,
)


class IncrementalBuildStrategy:
    """Build an incremental Semantic Layer revision.

    Previously this returned a stub dict (`{"triggerType": ...,
    "baseRevisionId": ..., ...}`) and never called an LLM at all. It
    now delegates to IncrementalBuilder, which is the component that
    actually talks to the LLM.
    """

    def __init__(self, builder: IncrementalBuilder) -> None:
        self._builder = builder

    def build(
        self,
        request: SemanticLayerGenerationRequest,
        sources: dict[str, Any],
        base_semantic_layer: dict[str, Any] | None = None,
    ) -> SemanticLayerBuildResponse:

        if request.trigger_type != "Incremental":
            raise ValueError(
                "IncrementalBuildStrategy requires "
                "trigger_type='Incremental'."
            )

        if not request.base_revision_id:
            raise ValueError(
                "base_revision_id is required for Incremental generation."
            )

        if not request.affected_objects:
            raise ValueError(
                "affected_objects is required for Incremental generation."
            )

        if base_semantic_layer is None:
            raise ValueError(
                "base_semantic_layer is required for Incremental generation."
            )

        return self._builder.build(
            base_semantic_layer=base_semantic_layer,
            affected_objects=[
                obj.to_dict() for obj in request.affected_objects
            ],
            updated_sources=sources,
        )
