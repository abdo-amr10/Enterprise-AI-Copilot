from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SemanticLayerRevision:
    """Represents one version of a Semantic Layer."""

    semantic_layer_id: str
    revision_id: str
    version: int
    status: str
    trigger_type: str
    semantic_layer: dict[str, Any]
    base_revision_id: str | None = None

    def __post_init__(self) -> None:
        if not self.semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")

        if not self.revision_id.strip():
            raise ValueError("revision_id cannot be empty.")

        if self.version < 1:
            raise ValueError("version must be greater than zero.")

        if self.status not in {
            "initial_draft",
            "pending_review",
            "approved",
            "rejected",
        }:
            raise ValueError(
                "Invalid semantic-layer revision status."
            )

        if self.trigger_type not in {
            "FullRebuild",
            "Incremental",
        }:
            raise ValueError(
                "trigger_type must be 'FullRebuild' or 'Incremental'."
            )

        if self.trigger_type == "Incremental" and not self.base_revision_id:
            raise ValueError(
                "base_revision_id is required for Incremental revisions."
            )

        if self.trigger_type == "FullRebuild" and self.base_revision_id:
            raise ValueError(
                "base_revision_id must not be set for FullRebuild revisions."
            )

        if not isinstance(self.semantic_layer, dict):
            raise ValueError(
                "semantic_layer must be a dictionary."
            )
