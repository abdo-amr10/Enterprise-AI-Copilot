from src.application.dto.semantic_layer.incremental_build_input import (
    IncrementalBuildInput,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.services.semantic_layer.builders.incremental_builder import (
    IncrementalBuilder,
)


class IncrementalBuildService:
    """Coordinates incremental Semantic Layer generation."""

    def __init__(
        self,
        builder: IncrementalBuilder,
    ) -> None:
        self._builder = builder

    def build(
        self,
        build_input: IncrementalBuildInput,
    ) -> SemanticLayerBuildResponse:
        """Build an incremental Semantic Layer draft."""

        return self._builder.build(
            base_semantic_layer=build_input.base_semantic_layer,
            affected_objects=build_input.affected_objects,
            updated_sources=build_input.updated_sources,
        )