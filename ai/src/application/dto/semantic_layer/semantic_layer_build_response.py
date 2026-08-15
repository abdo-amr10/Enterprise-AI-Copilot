"""Defines the output contract for semantic-layer construction."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SemanticLayerBuildResponse:
    """Represents a raw Semantic Layer draft produced by a builder.

    This response is intentionally identity-free: semantic_layer_id,
    revision_id, and base_revision_id are assigned afterwards by
    SemanticLayerGenerationPipeline, not by the builder itself.
    """

    semantic_layer: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.semantic_layer, dict):
            raise ValueError(
                "semantic_layer must be a dictionary."
            )

        if not self.semantic_layer:
            raise ValueError(
                "semantic_layer cannot be empty."
            )
