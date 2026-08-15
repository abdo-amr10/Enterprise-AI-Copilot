from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticLayerReviewResponse:
    """Represents the result of a Semantic Layer human review."""

    semantic_layer_id: str
    revision_id: str
    status: str
    version: str | None
    approved_by: str | None
    approved_at: str | None

    def __post_init__(self) -> None:
        """Validate the review response."""

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

        if self.approved_by is not None and not self.approved_by.strip():
            raise ValueError(
                "approved_by cannot be empty when provided."
            )

        if self.approved_at is not None and not self.approved_at.strip():
            raise ValueError(
                "approved_at cannot be empty when provided."
            )