from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticLayerRevisionResponse:
    """Represents a Semantic Layer revision returned by the Backend."""

    semantic_layer_id: str
    revision_id: str
    status: str
    version: str | None
    build_timestamp: str
    last_regeneration_type: str
    content: str
    created_at: str

    def __post_init__(self) -> None:
        """Validate the Semantic Layer revision response."""

        if not self.semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")

        if not self.revision_id.strip():
            raise ValueError("revision_id cannot be empty.")

        if not self.status.strip():
            raise ValueError("status cannot be empty.")

        if self.version is not None and not self.version.strip():
            raise ValueError(
                "version cannot be empty when provided."
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

        if not self.content.strip():
            raise ValueError("content cannot be empty.")

        if not self.created_at.strip():
            raise ValueError("created_at cannot be empty.")