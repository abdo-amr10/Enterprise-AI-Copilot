from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.services.semantic_layer.strategy.full_rebuild_strategy import (
    FullRebuildStrategy,
)
from src.application.services.semantic_layer.strategy.incremental_build_strategy import (
    IncrementalBuildStrategy,
)
from typing import Any


class SemanticLayerBuildService:
    """Selects the appropriate Semantic Layer build strategy."""

    def __init__(
        self,
        full_rebuild_strategy: FullRebuildStrategy,
        incremental_strategy: IncrementalBuildStrategy,
    ) -> None:
        self._full_rebuild_strategy = full_rebuild_strategy
        self._incremental_strategy = incremental_strategy

    def build(
        self,
        request: SemanticLayerGenerationRequest,
        sources: dict[str, Any],
        base_semantic_layer: dict[str, Any] | None = None,
    ) -> SemanticLayerBuildResponse:

        if request.trigger_type == "FullRebuild":
            return self._full_rebuild_strategy.build(
                request=request,
                sources=sources,
            )

        if base_semantic_layer is None:
            raise ValueError(
                "base_semantic_layer is required for Incremental generation."
            )

        return self._incremental_strategy.build(
            request=request,
            sources=sources,
            base_semantic_layer=base_semantic_layer,
        )
