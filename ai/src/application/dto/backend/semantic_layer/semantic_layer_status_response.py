from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticLayerStatusResponse:
    """Represents the current Semantic Layer status."""

    semantic_layer_id: str
    revision_id: str
    status: str
    version: str
    build_timestamp: str
    last_regeneration_type: str

    def __post_init__(self) -> None:
        """Validate the Semantic Layer status response."""

        if not self.semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")

        if not self.revision_id.strip():
            raise ValueError("revision_id cannot be empty.")

        if not self.status.strip():
            raise ValueError("status cannot be empty.")

        if not self.version.strip():
            raise ValueError("version cannot be empty.")

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