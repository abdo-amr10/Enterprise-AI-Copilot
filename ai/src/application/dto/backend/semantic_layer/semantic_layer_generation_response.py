from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticLayerGenerationResponse:
    """Represents the result of Semantic Layer draft generation."""

    status: str
    semantic_layer_id: str
    revision_id: str
    regenerated_objects_count: int
    build_timestamp: str
    last_regeneration_type: str
    affected_objects: tuple[dict[str, str], ...] = ()

    def __post_init__(self) -> None:
        """Validate the generation response."""

        if not self.status.strip():
            raise ValueError("status cannot be empty.")

        if not self.semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")

        if not self.revision_id.strip():
            raise ValueError("revision_id cannot be empty.")

        if self.regenerated_objects_count < 0:
            raise ValueError(
                "regenerated_objects_count cannot be negative."
            )

        if not self.build_timestamp.strip():
            raise ValueError("build_timestamp cannot be empty.")

        if self.last_regeneration_type not in {
            "FullRebuild",
            "Incremental",
        }:
            raise ValueError(
                "last_regeneration_type must be "
                "'FullRebuild' or 'Incremental'."
            )

        if self.last_regeneration_type == "FullRebuild" and self.affected_objects:
            raise ValueError(
                "affected_objects is only returned for Incremental generation."
            )
