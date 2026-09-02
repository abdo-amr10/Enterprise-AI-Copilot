"""Central Relationship Registry for tracking provided, inferred, and rejected relationships."""

from __future__ import annotations

from typing import Any
from src.application.services.semantic_layer.relationships.deduplicator import RelationshipDeduplicator
from src.application.services.semantic_layer.relationships.models import (
    ProcessedRelationship,
    RelationshipStatus,
)


class RelationshipRegistry:
    """Central registry maintaining relationship state, canonical identities, and audit records."""

    def __init__(self) -> None:
        self._provided: dict[tuple[tuple[str, str], tuple[str, str]], ProcessedRelationship] = {}
        self._inferred: dict[tuple[tuple[str, str], tuple[str, str]], ProcessedRelationship] = {}
        self._uncertain: dict[tuple[tuple[str, str], tuple[str, str]], ProcessedRelationship] = {}
        self._rejected: dict[tuple[tuple[str, str], tuple[str, str]], ProcessedRelationship] = {}

    def register_provided(self, relationship: ProcessedRelationship) -> None:
        """Register a backend-supplied relationship."""
        key = RelationshipDeduplicator.canonical_pair_key(
            relationship.source_table,
            relationship.source_column,
            relationship.target_table,
            relationship.target_column,
        )
        self._provided[key] = relationship

    def register_candidate(self, relationship: ProcessedRelationship) -> None:
        """Register a discovered candidate based on its classified status."""
        key = RelationshipDeduplicator.canonical_pair_key(
            relationship.source_table,
            relationship.source_column,
            relationship.target_table,
            relationship.target_column,
        )
        # Provided relationships always take precedence
        if key in self._provided:
            return

        if relationship.status == RelationshipStatus.INFERRED:
            self._inferred[key] = relationship
        elif relationship.status == RelationshipStatus.UNCERTAIN:
            self._uncertain[key] = relationship
        elif relationship.status == RelationshipStatus.NO_SUPPORTED_RELATIONSHIP:
            self._rejected[key] = relationship

    def is_registered(
        self,
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str,
    ) -> bool:
        """Check if a relationship pair is already registered (in any status)."""
        key = RelationshipDeduplicator.canonical_pair_key(
            source_table, source_column, target_table, target_column
        )
        return (
            key in self._provided
            or key in self._inferred
            or key in self._uncertain
            or key in self._rejected
        )

    def is_provided(
        self,
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str,
    ) -> bool:
        """Check if a pair is already registered as a provided relationship."""
        key = RelationshipDeduplicator.canonical_pair_key(
            source_table, source_column, target_table, target_column
        )
        return key in self._provided

    def get_executable_relationships(self) -> list[ProcessedRelationship]:
        """Return only relationships marked as executable for SQL join paths."""
        return [
            rel for rel in (*self._provided.values(), *self._inferred.values())
            if rel.is_executable
        ]

    def get_all_relationships(self) -> list[ProcessedRelationship]:
        """Return all valid (non-rejected) relationships for semantic modeling."""
        return [*self._provided.values(), *self._inferred.values(), *self._uncertain.values()]

    def get_rejected_candidates(self) -> list[ProcessedRelationship]:
        """Return rejected candidates for audit and diagnostics."""
        return list(self._rejected.values())

    def to_dict(self) -> dict[str, Any]:
        """Export registry contents to JSON-serializable dictionary."""
        return {
            "provided_count": len(self._provided),
            "inferred_count": len(self._inferred),
            "uncertain_count": len(self._uncertain),
            "rejected_count": len(self._rejected),
            "provided": [rel.to_output_dict() for rel in self._provided.values()],
            "inferred": [rel.to_output_dict() for rel in self._inferred.values()],
            "uncertain": [rel.to_output_dict() for rel in self._uncertain.values()],
            "rejected": [rel.to_output_dict() for rel in self._rejected.values()],
        }
