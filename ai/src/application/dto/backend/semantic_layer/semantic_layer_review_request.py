from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticLayerReviewRequest:
    """Defines a human review decision for a Semantic Layer revision."""

    semantic_layer_id: str
    revision_id: str
    decision: str
    comments: str | None = None

    def __post_init__(self) -> None:
        """Validate the review request."""

        if not self.semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")

        if not self.revision_id.strip():
            raise ValueError("revision_id cannot be empty.")

        if self.decision not in {
            "Approve",
            "Reject",
        }:
            raise ValueError(
                "decision must be Approve or Reject."
            )

        if self.decision == "Reject":
            if self.comments is None or not self.comments.strip():
                raise ValueError(
                    "comments are required when rejecting a revision."
                )