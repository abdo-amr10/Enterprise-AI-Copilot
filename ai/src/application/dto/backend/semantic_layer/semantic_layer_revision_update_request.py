from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticLayerRevisionUpdateRequest:
    """Defines the edited content of a Semantic Layer revision."""

    semantic_layer_id: str
    revision_id: str
    content: str

    def __post_init__(self) -> None:
        """Validate the revision update request."""

        if not self.semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")

        if not self.revision_id.strip():
            raise ValueError("revision_id cannot be empty.")

        if not self.content.strip():
            raise ValueError("content cannot be empty.")