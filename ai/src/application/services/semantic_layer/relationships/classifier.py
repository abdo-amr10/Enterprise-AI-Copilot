"""Relationship classification and categorization into the six canonical cases."""

from __future__ import annotations

from typing import Any
from src.application.services.semantic_layer.relationships.models import (
    EvidenceBreakdown,
    ProcessedRelationship,
    ProvenanceSource,
    RelationshipCase,
    RelationshipStatus,
    ScoringConfig,
)


class RelationshipClassifier:
    """Classifies candidate relationships into status and explicit relationship cases."""

    def __init__(self, config: ScoringConfig | None = None) -> None:
        self.config = config or ScoringConfig()

    def classify_inferred_candidate(
        self,
        candidate_id: str,
        name: str,
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str,
        confidence: float,
        evidence: EvidenceBreakdown,
        is_ambiguous: bool = False,
        schema_version: str = "1.0",
    ) -> ProcessedRelationship:
        """Classify a scored candidate relationship.

        Evaluates against the six relationship cases:
        1. Provided Relationship (Handled in deduplicator)
        2. Metadata-Confirmed Relationship
        3. Strongly Inferred Relationship
        4. Probabilistic / Approximate Relationship
        5. Uncertain / Ambiguous Relationship
        6. No Supported Relationship
        """
        # Case 5: Ambiguous / multiple competing targets
        if is_ambiguous:
            status = RelationshipStatus.UNCERTAIN
            rel_case = RelationshipCase.UNCERTAIN_AMBIGUOUS
            is_executable = False
            inference_method = "AMBIGUOUS_MULTI_TARGET"
        # Case 6: Score below minimum threshold
        elif confidence < self.config.probabilistic_threshold:
            status = RelationshipStatus.NO_SUPPORTED_RELATIONSHIP
            rel_case = RelationshipCase.NO_SUPPORTED_RELATIONSHIP
            is_executable = False
            inference_method = "REJECTED_INSUFFICIENT_EVIDENCE"
        # Case 4: Probabilistic / Approximate
        elif confidence < self.config.strong_inference_threshold:
            status = RelationshipStatus.UNCERTAIN
            rel_case = RelationshipCase.PROBABILISTIC_APPROXIMATE
            is_executable = False
            inference_method = "PROBABILISTIC_EVIDENCE"
        # Case 3: Strongly Inferred
        else:
            status = RelationshipStatus.INFERRED
            rel_case = RelationshipCase.STRONGLY_INFERRED
            is_executable = self.config.allow_executable_inferred
            inference_method = "MULTIDIMENSIONAL_INFERENCE"

        # Determine cardinality
        cardinality = "1:N" if evidence.pk_signal >= 0.8 else "unknown"

        return ProcessedRelationship(
            id=candidate_id,
            name=name,
            source_table=source_table,
            source_column=source_column,
            target_table=target_table,
            target_column=target_column,
            status=status,
            relationship_case=rel_case,
            relationship_type="foreign_key" if is_executable else "candidate",
            cardinality=cardinality,
            confidence=confidence,
            evidence=evidence,
            inference_method=inference_method,
            provenance={
                "source": ProvenanceSource.INFERENCE_ENGINE.value,
                "authoritative": False,
            },
            schema_version=schema_version,
            is_executable=is_executable,
        )
