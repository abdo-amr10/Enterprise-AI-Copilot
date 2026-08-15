"""Application service for assigning semantic-layer revision metadata."""

from __future__ import annotations

from typing import Any

from src.infrastructure.semantic_layer.persistence.semantic_layer_id_generator import (
    SemanticLayerIdGenerator,
)


class SemanticLayerMetadataService:
    """Create and update semantic-layer identity metadata.

    This is the ONLY place semantic_layer_id and revision_id are
    minted for a working draft. It is called once per Generation
    Pipeline run, right after building/merging, before the draft is
    handed to Validation.

    `version` is intentionally NOT assigned here: a working draft does
    not need a sequential version while it moves through Validation,
    Review, and Embedding. version is only meaningful once a revision
    is persisted, and is assigned then by SemanticLayerRevisionService
    using a number the persistence layer supplies.
    """

    def __init__(
        self,
        id_generator: SemanticLayerIdGenerator,
    ) -> None:
        self._id_generator = id_generator

    def initialize(
        self,
        semantic_layer: dict[str, Any],
        semantic_layer_id: str,
    ) -> dict[str, Any]:
        """Initialize a FullRebuild revision for an uploaded Semantic Layer."""

        if not semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")

        result = dict(semantic_layer)

        metadata = dict(result.get("metadata", {}))

        metadata.update(
            {
                "semantic_layer_id": semantic_layer_id,
                "revision_id": (
                    self._id_generator.generate_revision_id()
                ),
                "base_revision_id": None,
                "trigger_type": "FullRebuild",
                "status": "initial_draft",
                "validated": False,
                "human_review_required": True,
            }
        )

        result["metadata"] = metadata

        return result

    def create_revision(
        self,
        semantic_layer: dict[str, Any],
        semantic_layer_id: str,
        base_revision_id: str,
    ) -> dict[str, Any]:
        """Assign a new revision to an existing Semantic Layer
        (Incremental: same lineage, so semantic_layer_id is reused from
        the request and base_revision_id links back to the revision
        this update is based on)."""

        if not semantic_layer_id.strip():
            raise ValueError(
                "semantic_layer_id cannot be empty."
            )

        if not base_revision_id.strip():
            raise ValueError(
                "base_revision_id cannot be empty."
            )

        result = dict(semantic_layer)

        metadata = dict(result.get("metadata", {}))

        metadata.update(
            {
                "semantic_layer_id": semantic_layer_id,
                "revision_id": (
                    self._id_generator.generate_revision_id()
                ),
                "base_revision_id": base_revision_id,
                "trigger_type": "Incremental",
                "status": "initial_draft",
                "validated": False,
                "human_review_required": True,
            }
        )

        result["metadata"] = metadata

        return result
