"""Package an approved Semantic Layer draft into a persisted revision."""

from __future__ import annotations

from typing import Any


class SemanticLayerRevisionService:
    """Wrap a Semantic Layer draft into a persisted revision record.

    This service does NOT generate identifiers. semantic_layer_id and
    revision_id are already present on the draft's metadata — they
    were assigned earlier, during generation, by
    SemanticLayerMetadataService. Generating a new revision_id here
    (as the previous version of this file did, via RevisionIdGenerator)
    would give the same revision two different revision_ids depending
    on whether you looked at the working draft or the persisted
    record — that bug is why RevisionIdGenerator has been removed.

    `version` is still supplied by the caller: this service has no
    persistence access, so it cannot know the next sequential number
    for a Semantic Layer's lineage. The caller (the component with
    repository access) is responsible for computing it.
    """

    def create_revision(
        self,
        semantic_layer_id: str,
        revision_id: str,
        semantic_layer: dict[str, Any],
        trigger_type: str,
        version: int,
        status: str = "initial_draft",
        base_revision_id: str | None = None,
    ) -> dict[str, Any]:
        """Create revision data around a generated Semantic Layer.

        Keys are snake_case throughout, matching every other DTO/entity
        in the project (SemanticLayerRevision, metadata, etc.) — the
        previous camelCase output (`semanticLayerId`, `revisionId`, ...)
        could never be unpacked directly into `SemanticLayerRevision(**...)`
        and has been fixed here.
        """

        if not semantic_layer_id.strip():
            raise ValueError(
                "semantic_layer_id cannot be empty."
            )

        if not revision_id.strip():
            raise ValueError(
                "revision_id cannot be empty."
            )

        if not semantic_layer:
            raise ValueError(
                "semantic_layer cannot be empty."
            )

        if version < 1:
            raise ValueError(
                "version must be greater than zero."
            )

        if trigger_type == "Incremental" and not base_revision_id:
            raise ValueError(
                "base_revision_id is required for Incremental revisions."
            )

        if trigger_type == "FullRebuild" and base_revision_id:
            raise ValueError(
                "base_revision_id must not be set for FullRebuild revisions."
            )

        return {
            "semantic_layer_id": semantic_layer_id,
            "revision_id": revision_id,
            "version": version,
            "status": status,
            "trigger_type": trigger_type,
            "base_revision_id": base_revision_id,
            "semantic_layer": semantic_layer,
        }
