"""Application boundary for Semantic Layer build strategies."""

from typing import Any, Protocol

from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)


class SemanticLayerBuildStrategy(Protocol):
    """Defines the contract for building a Semantic Layer draft.

    Both FullRebuildStrategy and IncrementalBuildStrategy implement this
    same signature. `base_semantic_layer` is required by Incremental
    strategies and ignored by FullRebuild strategies, but every strategy
    accepts it so callers (SemanticLayerBuildService) can treat all
    strategies uniformly.
    """

    def build(
        self,
        request: SemanticLayerGenerationRequest,
        sources: dict[str, Any],
        base_semantic_layer: dict[str, Any] | None = None,
    ) -> SemanticLayerBuildResponse:
        """Build a raw Semantic Layer draft according to the selected strategy.

        Args:
            request: Semantic Layer generation configuration.
            sources: Source data required to build the draft (schema,
                relationships, documentation, business glossary, sample
                data).
            base_semantic_layer: The current approved Semantic Layer.
                Required when `request.trigger_type == "Incremental"`,
                ignored for `"FullRebuild"`.

        Returns:
            A raw, identity-free Semantic Layer draft. Identity fields
            (semantic_layer_id, revision_id, version) are assigned later
            by SemanticLayerGenerationPipeline, not by the strategy.
        """
        ...
