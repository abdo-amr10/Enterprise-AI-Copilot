"""Relationship and Schema Processing Engine.

Provides input validation, schema normalization, canonical deduplication,
evidence-based candidate discovery, sample data analysis, scoring, classification,
relationship registry, graph modeling, and disconnected component detection.
"""

from src.application.services.semantic_layer.relationships.models import (
    BackendDatabaseSchema,
    BackendTableSchema,
    BackendColumnSchema,
    BackendRelationshipSchema,
    RelationshipStatus,
    RelationshipCase,
    ProvenanceSource,
    ProcessedRelationship,
    EvidenceBreakdown,
    ScoringConfig,
    NormalizedSchema,
    NormalizedTable,
    NormalizedColumn,
    DisconnectedAnalysisResult,
)

from src.application.services.semantic_layer.relationships.relationship_service import (
    RelationshipProcessingEngine,
    RelationshipProcessingResult,
)

__all__ = [
    "BackendDatabaseSchema",
    "BackendTableSchema",
    "BackendColumnSchema",
    "BackendRelationshipSchema",
    "RelationshipStatus",
    "RelationshipCase",
    "ProvenanceSource",
    "ProcessedRelationship",
    "EvidenceBreakdown",
    "ScoringConfig",
    "NormalizedSchema",
    "NormalizedTable",
    "NormalizedColumn",
    "DisconnectedAnalysisResult",
    "RelationshipProcessingEngine",
    "RelationshipProcessingResult",
]
