from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticLayerRevisionUpdateResponse:
    """Represents the result of updating a Semantic Layer revision."""

    semantic_layer_id: str
    revision_id: str
    status: str
    message: str

    def __post_init__(self) -> None:
        """Validate the revision update response."""

        if not self.semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")

        if not self.revision_id.strip():
            raise ValueError("revision_id cannot be empty.")

        if not self.status.strip():
            raise ValueError("status cannot be empty.")

        if not self.message.strip():
            raise ValueError("message cannot be empty.")