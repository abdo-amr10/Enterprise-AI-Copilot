"""Backend-facing request DTO for Semantic Layer generation.

This is the single, authoritative version of this DTO. The earlier
duplicate (`semantic_layer_generation_request.py`, which carried its
own `AffectedObject` shape and a required `revision_id`) has been
removed. Every layer that builds a Semantic Layer draft imports the
request type from here.
"""

from dataclasses import dataclass, field
from typing import Any


_VALID_SECTIONS = {
    "entities",
    "relationships",
    "measures",
    "dimensions",
    "business_rules",
}

_VALID_ACTIONS = {"upsert", "delete"}


@dataclass(frozen=True)
class AffectedObject:
    """Identifies a single semantic-layer object touched by an
    Incremental update.

    This is the one canonical shape for "affected objects" across the
    whole project (request, IncrementalBuildInput, IncrementalBuilder,
    and SemanticLayerMergeService all use this same dataclass / its
    dict form).

    action vocabulary is intentionally just {"upsert", "delete"} to
    match SemanticLayerMergeService's merge semantics: "upsert" adds
    or replaces an object, "delete" removes it. There is no separate
    "add" vs "update" — the merge is keyed by name, so both collapse
    into "upsert".
    """

    object_id: str
    section: str
    name: str
    action: str

    def __post_init__(self) -> None:
        if not self.object_id.strip():
            raise ValueError("object_id cannot be empty.")

        if self.section not in _VALID_SECTIONS:
            raise ValueError(
                f"section must be one of {sorted(_VALID_SECTIONS)}."
            )

        if not self.name.strip():
            raise ValueError("name cannot be empty.")

        if self.action not in _VALID_ACTIONS:
            raise ValueError(
                f"action must be one of {sorted(_VALID_ACTIONS)}."
            )

    def to_dict(self) -> dict[str, str]:
        """Plain-dict form, used by IncrementalBuilder's prompt and by
        SemanticLayerMergeService, which both operate on dicts rather
        than this dataclass directly."""

        return {
            "object_id": self.object_id,
            "section": self.section,
            "name": self.name,
            "action": self.action,
        }


@dataclass(frozen=True)
class SemanticLayerGenerationRequest:
    """Backend request to generate a new Semantic Layer revision.

    Identity ownership:
        `semantic_layer_id`, `revision_id`, and `version` are owned
        exclusively by the AI service (see
        `SemanticLayerGenerationPipeline._assign_identity`). This
        request intentionally has NO `revision_id` and NO `version`
        field — the Backend never supplies them for a new revision.

        The Backend only supplies identifiers it already holds because
        the AI returned them on a previous call:

        - `semantic_layer_id`: required for Incremental (identifies the
          existing Semantic Layer being updated). Must be omitted for
          FullRebuild, since a brand-new semantic_layer_id is minted.
        - `base_revision_id`: required for Incremental (the previously
          issued revision_id this update is based on). Must be omitted
          for FullRebuild.

        `source_file_ids` is likewise Backend-owned: the AI never
        generates or manages it, only uses it as a reference.
    """

    trigger_type: str
    source_file_ids: tuple[str, ...]
    semantic_layer_id: str | None = None
    base_revision_id: str | None = None
    affected_objects: tuple[AffectedObject, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.trigger_type not in {"FullRebuild", "Incremental"}:
            raise ValueError(
                "trigger_type must be 'FullRebuild' or 'Incremental'."
            )

        if not isinstance(self.source_file_ids, tuple) or not self.source_file_ids:
            raise ValueError("source_file_ids cannot be empty.")

        if self.trigger_type == "Incremental":
            if not self.semantic_layer_id:
                raise ValueError(
                    "semantic_layer_id is required for Incremental requests."
                )
            if not self.base_revision_id:
                raise ValueError(
                    "base_revision_id is required for Incremental requests."
                )
            if not self.affected_objects:
                raise ValueError(
                    "affected_objects cannot be empty for Incremental requests."
                )

        if self.trigger_type == "FullRebuild":
            if self.semantic_layer_id:
                raise ValueError(
                    "semantic_layer_id must not be set for FullRebuild requests."
                )
            if self.base_revision_id:
                raise ValueError(
                    "base_revision_id must not be set for FullRebuild requests."
                )
            if self.affected_objects:
                raise ValueError(
                    "affected_objects must not be set for FullRebuild requests."
                )
