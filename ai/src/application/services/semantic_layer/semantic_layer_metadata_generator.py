"""Application service for assigning semantic-layer revision metadata."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

class SemanticLayerMetadataService:
    """Create and update semantic-layer identity metadata.

    Backend supplies semantic-layer and revision IDs. This service copies
    those immutable lineage values into an in-memory draft; it never mints
    IDs or assigns a lifecycle version.
    """

    def initialize(
        self,
        semantic_layer: dict[str, Any],
        semantic_layer_id: str,
        revision_id: str,
    ) -> dict[str, Any]:
        """Initialize a FullRebuild revision for an uploaded Semantic Layer."""

        if not semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")
        if not revision_id.strip():
            raise ValueError("revision_id cannot be empty.")

        result = deepcopy(semantic_layer)

        metadata = dict(result.get("metadata", {}))

        metadata.update(
            {
                "semantic_layer_id": semantic_layer_id,
                "revision_id": revision_id,
                "base_revision_id": None,
                "trigger_type": "FullRebuild",
                "status": "initial_draft",
                "validated": False,
                "human_review_required": True,
            }
        )

        result["metadata"] = metadata

        return result

    def prepare_draft(
        self,
        semantic_layer: dict[str, Any],
        semantic_layer_id: str,
        trigger_type: str,
        base_revision_id: str | None = None,
    ) -> dict[str, Any]:
        """Prepare AI-generated content before Backend creates a revision.

        Revision identity is intentionally absent: it is created by Backend
        persistence after this unpersisted draft is returned.
        """

        if not semantic_layer_id or not semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")
        result = deepcopy(semantic_layer)
        metadata = dict(result.get("metadata", {}))
        metadata.update(
            {
                "semantic_layer_id": semantic_layer_id,
                "base_revision_id": base_revision_id,
                "trigger_type": trigger_type,
                "status": "initial_draft",
                "validated": False,
                "human_review_required": True,
            }
        )
        metadata.pop("revision_id", None)
        result["metadata"] = metadata
        return result

    def create_revision(
        self,
        semantic_layer: dict[str, Any],
        semantic_layer_id: str,
        revision_id: str,
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
        if not revision_id.strip():
            raise ValueError("revision_id cannot be empty.")

        result = deepcopy(semantic_layer)

        metadata = dict(result.get("metadata", {}))

        metadata.update(
            {
                "semantic_layer_id": semantic_layer_id,
                "revision_id": revision_id,
                "base_revision_id": base_revision_id,
                "trigger_type": "Incremental",
                "status": "initial_draft",
                "validated": False,
                "human_review_required": True,
            }
        )

        result["metadata"] = metadata

        return result
