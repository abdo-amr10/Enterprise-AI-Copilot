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

@dataclass(frozen=True)
class AffectedObject:
    """Identifies a single semantic-layer object touched by an
    Incremental update.

    This is the one canonical shape for "affected objects" across the
    whole project (request, IncrementalBuildInput, IncrementalBuilder,
    and SemanticLayerMergeService all use this same dataclass / its
    dict form).

    ``add`` creates a named object, while ``update`` and ``delete`` address
    an existing stable object ID. This makes the requested mutation explicit
    and prevents a generated draft from changing unrelated objects.
    """

    section: str
    action: str = "update"
    id: str | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        if self.section not in _VALID_SECTIONS:
            raise ValueError(
                f"section must be one of {sorted(_VALID_SECTIONS)}."
            )

        if self.action not in {"add", "update", "delete"}:
            raise ValueError("action must be add, update, or delete.")
        if self.action in {"update", "delete"} and (not self.id or not self.id.strip()):
            raise ValueError("id is required for update and delete operations.")
        if self.action == "add" and (not self.name or not self.name.strip()):
            raise ValueError("name is required for add operations.")

    def to_dict(self) -> dict[str, str]:
        """Plain-dict form, used by IncrementalBuilder's prompt and by
        SemanticLayerMergeService, which both operate on dicts rather
        than this dataclass directly."""

        result = {
            "section": self.section,
            "action": self.action,
        }
        if self.id:
            result["id"] = self.id
        if self.name:
            result["name"] = self.name
        return result


@dataclass(frozen=True)
class SemanticLayerGenerationRequest:
    """Backend request to generate a new Semantic Layer revision.

    Identity ownership:
        `semantic_layer_id`, `revision_id`, and `version` are owned by
        Backend. The AI receives the first two as immutable lineage inputs
        and never generates or replaces them. Backend assigns the lifecycle
        version when it persists the returned draft.
        - `base_revision_id`: required for Incremental (the previously
          issued revision_id this update is based on). Must be omitted
          for FullRebuild.

        `source_file_ids` is likewise Backend-owned: the AI never
        generates or manages it, only uses it as a named mapping from
        source type (schema, documentation, glossary, sampleData) to file ID.
    """

    trigger_type: str
    source_file_ids: dict[str, str]
    semantic_layer_id: str | None = None
    revision_id: str | None = None
    base_revision_id: str | None = None
    affected_objects: tuple[AffectedObject, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.trigger_type not in {"FullRebuild", "Incremental"}:
            raise ValueError(
                "trigger_type must be 'FullRebuild' or 'Incremental'."
            )

        if not isinstance(self.source_file_ids, dict):
            raise ValueError("source_file_ids must be an object.")

        allowed_source_types = {
            "schema",
            "documentation",
            "glossary",
            "sampleData",
        }
        unknown_source_types = set(self.source_file_ids) - allowed_source_types
        if unknown_source_types:
            raise ValueError(
                "source_file_ids contains unknown source types: "
                f"{sorted(unknown_source_types)}."
            )
        if not isinstance(self.source_file_ids.get("schema"), str) or not self.source_file_ids["schema"].strip():
            raise ValueError("source_file_ids.schema is required.")
        if any(
            not isinstance(file_id, str) or not file_id.strip()
            for file_id in self.source_file_ids.values()
        ):
            raise ValueError("source_file_ids values must be non-empty file IDs.")

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
            if not self.semantic_layer_id:
                raise ValueError(
                    "semantic_layer_id is required for FullRebuild requests."
                )
            if self.base_revision_id:
                raise ValueError(
                    "base_revision_id must not be set for FullRebuild requests."
                )
            if self.affected_objects:
                raise ValueError(
                    "affected_objects must not be set for FullRebuild requests."
                )
