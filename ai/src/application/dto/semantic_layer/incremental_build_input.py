from dataclasses import dataclass
from typing import Any

from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    AffectedObject,
)


@dataclass(frozen=True)
class IncrementalBuildInput:
    """Input required for an incremental Semantic Layer update.

    affected_objects uses the same AffectedObject shape as the Backend
    request (object_id, section, name, action) — this is the one
    canonical shape used everywhere in the Incremental path.
    """

    base_semantic_layer: dict[str, Any]
    affected_objects: tuple[AffectedObject, ...]
    updated_sources: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.base_semantic_layer, dict):
            raise ValueError(
                "base_semantic_layer must be a dictionary."
            )

        if not self.base_semantic_layer:
            raise ValueError(
                "base_semantic_layer cannot be empty."
            )

        if not isinstance(self.affected_objects, tuple):
            raise ValueError(
                "affected_objects must be a tuple."
            )

        if not self.affected_objects:
            raise ValueError(
                "affected_objects cannot be empty."
            )

        if not all(
            isinstance(item, AffectedObject) for item in self.affected_objects
        ):
            raise ValueError(
                "Every item in affected_objects must be an AffectedObject."
            )

        if not isinstance(self.updated_sources, dict):
            raise ValueError(
                "updated_sources must be a dictionary."
            )
