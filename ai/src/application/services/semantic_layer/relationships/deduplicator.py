"""Canonical identity and deduplication for database relationships."""

from __future__ import annotations

from typing import Any
from src.application.services.semantic_layer.relationships.models import (
    BackendRelationshipSchema,
    EvidenceBreakdown,
    NormalizedSchema,
    ProcessedRelationship,
    ProvenanceSource,
    RelationshipCase,
    RelationshipStatus,
)
from src.application.services.semantic_layer.relationships.normalizer import SchemaNormalizer


class RelationshipDeduplicator:
    """Provides canonical identity hashing and deduplication for relationships."""

    @staticmethod
    def canonical_pair_key(
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str,
    ) -> tuple[tuple[str, str], tuple[str, str]]:
        """Compute an order-independent canonical key for two column endpoints.

        Ensures that:
            customers.customer_id -> orders.customer_id
        and
            orders.customer_id -> customers.customer_id
        produce the exact same canonical identity.
        """
        norm_a = (SchemaNormalizer.normalize_identifier(source_table), SchemaNormalizer.normalize_identifier(source_column))
        norm_b = (SchemaNormalizer.normalize_identifier(target_table), SchemaNormalizer.normalize_identifier(target_column))
        return tuple(sorted([norm_a, norm_b]))  # type: ignore[return-value]

    @classmethod
    def process_provided_relationship(
        cls,
        rel: BackendRelationshipSchema,
        schema: NormalizedSchema,
        schema_version: str = "1.0",
    ) -> ProcessedRelationship:
        """Validate and process a backend-supplied relationship.

        Phase 3 rule:
        - Must be structurally validated (source/target tables and columns must exist).
        - status = PROVIDED
        - confidence = 1.0
        - provenance = BACKEND_SCHEMA
        - Never silently invent a replacement.
        """
        source_table_obj = SchemaNormalizer.find_table_by_name(schema, rel.from_table)
        if not source_table_obj:
            raise ValueError(
                f"Provided relationship references unknown source table '{rel.from_table}'."
            )

        source_col_obj = SchemaNormalizer.find_column_by_name(source_table_obj, rel.from_column)
        if not source_col_obj:
            raise ValueError(
                f"Provided relationship references unknown source column '{rel.from_table}.{rel.from_column}'."
            )

        target_table_obj = SchemaNormalizer.find_table_by_name(schema, rel.to_table)
        if not target_table_obj:
            raise ValueError(
                f"Provided relationship references unknown target table '{rel.to_table}'."
            )

        target_col_obj = SchemaNormalizer.find_column_by_name(target_table_obj, rel.to_column)
        if not target_col_obj:
            raise ValueError(
                f"Provided relationship references unknown target column '{rel.to_table}.{rel.to_column}'."
            )

        # Preserve the original physical table and column names
        phys_source_table = source_table_obj.original_name
        phys_source_col = source_col_obj.original_name
        phys_target_table = target_table_obj.original_name
        phys_target_col = target_col_obj.original_name

        rel_name = rel.name or f"{phys_source_table}_{phys_target_table}_{phys_source_col}"

        evidence = EvidenceBreakdown(
            name_similarity=1.0,
            normalized_similarity=1.0,
            type_compatibility=1.0,
            pk_signal=1.0 if target_col_obj.is_primary_key or source_col_obj.is_primary_key else 0.5,
            fk_naming_pattern=1.0,
            semantic_similarity=1.0,
            explanations=["Explicitly declared and validated in backend source schema."],
        )

        return ProcessedRelationship(
            id=f"rel-provided-{phys_source_table}-{phys_source_col}-{phys_target_table}-{phys_target_col}",
            name=rel_name,
            source_table=phys_source_table,
            source_column=phys_source_col,
            target_table=phys_target_table,
            target_column=phys_target_col,
            status=RelationshipStatus.PROVIDED,
            relationship_case=RelationshipCase.PROVIDED,
            relationship_type=rel.relationship_type or "foreign_key",
            cardinality=rel.cardinality or "1:N",
            confidence=1.0,
            evidence=evidence,
            inference_method="DIRECT_BACKEND_METADATA",
            provenance={
                "source": ProvenanceSource.BACKEND_SCHEMA.value,
                "authoritative": True,
                "security_propagation": rel.security_propagation,
                "predicate_equivalence": rel.predicate_equivalence,
            },
            schema_version=schema_version,
            is_executable=True,
        )
