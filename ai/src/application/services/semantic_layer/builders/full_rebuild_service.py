from src.application.dto.semantic_layer.semantic_layer_build_input import (
    SemanticLayerBuildInput,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.services.semantic_layer.builders.full_build_builder import (
    FullRebuildBuilder,
)


class FullRebuildService:
    """Coordinates complete Semantic Layer generation."""

    def __init__(
        self,
        builder: FullRebuildBuilder,
    ) -> None:
        self._builder = builder

    def build(
        self,
        build_input: SemanticLayerBuildInput,
    ) -> SemanticLayerBuildResponse:
        """Build an initial Semantic Layer using all available sources."""

        return self._builder.build(build_input)