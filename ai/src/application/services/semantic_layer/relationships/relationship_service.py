"""Relationship Processing Engine orchestrating Phases 1 through 14."""

from __future__ import annotations

from typing import Any
from pydantic import ValidationError

from src.application.services.semantic_layer.relationships.candidate_discovery import (
    CandidateDiscoveryEngine,
)
from src.application.services.semantic_layer.relationships.classifier import (
    RelationshipClassifier,
)
from src.application.services.semantic_layer.relationships.deduplicator import (
    RelationshipDeduplicator,
)
from src.application.services.semantic_layer.relationships.graph import (
    RelationshipGraph,
)
from src.application.services.semantic_layer.relationships.models import (
    BackendDatabaseSchema,
    BackendRelationshipSchema,
    DisconnectedAnalysisResult,
    NormalizedSchema,
    ProcessedRelationship,
    ScoringConfig,
)
from src.application.services.semantic_layer.relationships.normalizer import (
    SchemaNormalizer,
)
from src.application.services.semantic_layer.relationships.registry import (
    RelationshipRegistry,
)
from src.application.services.semantic_layer.relationships.sample_data_analyzer import (
    SampleDataAnalyzer,
)
from src.application.services.semantic_layer.relationships.scorer import (
    RelationshipScorer,
)


class RelationshipProcessingResult:
    """Encapsulates the complete result of schema and relationship processing."""

    def __init__(
        self,
        normalized_schema: NormalizedSchema,
        relationships: list[ProcessedRelationship],
        registry: RelationshipRegistry,
        graph: RelationshipGraph,
        disconnected_analysis: DisconnectedAnalysisResult,
    ) -> None:
        self.normalized_schema = normalized_schema
        self.relationships = relationships
        self.registry = registry
        self.graph = graph
        self.disconnected_analysis = disconnected_analysis

    def to_semantic_layer_relationships(self) -> list[dict[str, Any]]:
        """Return relationships formatted for the Semantic Layer draft and revision."""
        return [rel.to_output_dict() for rel in self.relationships]

    def to_executable_relationships(self) -> list[dict[str, Any]]:
        """Return only relationships safe for automatic SQL JOIN execution."""
        return [
            rel.to_output_dict()
            for rel in self.relationships
            if rel.is_executable
        ]


class RelationshipProcessingEngine:
    """Main orchestration engine for schema validation, normalization, and relationship processing."""

    def __init__(self, config: ScoringConfig | None = None) -> None:
        self.config = config or ScoringConfig()
        self.scorer = RelationshipScorer(self.config)
        self.classifier = RelationshipClassifier(self.config)
        self.discovery_engine = CandidateDiscoveryEngine(
            scorer=self.scorer,
            classifier=self.classifier,
            config=self.config,
        )

    def process(
        self,
        raw_schema: dict[str, Any],
        explicit_relationships: list[dict[str, Any]] | None = None,
        sample_data: Any | None = None,
        glossary_terms: list[str] | None = None,
    ) -> RelationshipProcessingResult:
        """Execute the full relationship processing pipeline.

        Args:
            raw_schema: Raw database schema payload from backend or files.
            explicit_relationships: Optional separate relationships list.
            sample_data: Optional empirical sample data.
            glossary_terms: Optional list of business glossary terms.

        Returns:
            RelationshipProcessingResult containing normalized schema, relationships,
            registry, graph, and disconnected entity analysis.
        """
        # 1. Phase 1: Input Validation
        validated_schema = self._validate_input_schema(raw_schema, explicit_relationships)

        # 2. Phase 2: Schema Normalization
        normalized_schema = SchemaNormalizer.normalize_schema(validated_schema)

        # 3. Phase 11: Central Relationship Registry
        registry = RelationshipRegistry()

        # 4. Phase 3 & 4: Process and Deduplicate Provided Relationships
        for rel_schema in validated_schema.relationships:
            processed_rel = RelationshipDeduplicator.process_provided_relationship(
                rel=rel_schema,
                schema=normalized_schema,
                schema_version=validated_schema.version,
            )
            registry.register_provided(processed_rel)

        # 5. Phase 6: Optional Sample Data Analyzer
        sample_analyzer = SampleDataAnalyzer(sample_data) if sample_data else None

        # 6. Phase 5, 7, 8, 9, 10: Candidate Discovery, Scoring, and Classification
        self.discovery_engine.discover_candidates(
            schema=normalized_schema,
            registry=registry,
            sample_analyzer=sample_analyzer,
            glossary_terms=glossary_terms,
        )

        all_relationships = registry.get_all_relationships()

        # 7. Phase 12 & 13: Build Graph and Detect Disconnected Entities
        graph = RelationshipGraph(
            schema=normalized_schema,
            relationships=all_relationships,
        )
        disconnected_analysis = graph.analyze_connectivity()

        return RelationshipProcessingResult(
            normalized_schema=normalized_schema,
            relationships=all_relationships,
            registry=registry,
            graph=graph,
            disconnected_analysis=disconnected_analysis,
        )

    @staticmethod
    def _validate_input_schema(
        raw_schema: dict[str, Any],
        explicit_relationships: list[dict[str, Any]] | None = None,
    ) -> BackendDatabaseSchema:
        """Validate input dictionary using Pydantic, tolerating missing/empty relationships."""
        if not isinstance(raw_schema, dict):
            raise ValueError("Schema must be a dictionary.")

        schema_copy = dict(raw_schema)

        # Handle relationships passed separately or inside schema
        rels = explicit_relationships if explicit_relationships is not None else schema_copy.get("relationships", [])
        if rels is None:
            rels = []
        if not isinstance(rels, list):
            raise ValueError("Relationships must be a list when provided.")

        schema_copy["relationships"] = rels

        try:
            return BackendDatabaseSchema.model_validate(schema_copy)
        except ValidationError as error:
            raise ValueError(f"Schema validation error: {error}") from error
