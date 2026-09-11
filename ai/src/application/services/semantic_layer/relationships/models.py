"""Data models and validation schemas for relationship processing and candidate discovery."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


class RelationshipStatus(str, Enum):
    """Lifecycle and confidence state of a relationship."""

    PROVIDED = "PROVIDED"
    INFERRED = "INFERRED"
    UNCERTAIN = "UNCERTAIN"
    NO_SUPPORTED_RELATIONSHIP = "NO_SUPPORTED_RELATIONSHIP"
    METADATA_UNAVAILABLE = "METADATA_UNAVAILABLE"


class RelationshipCase(str, Enum):
    """The six explicit relationship classification cases."""

    PROVIDED = "Provided Relationship"
    METADATA_CONFIRMED = "Metadata-Confirmed Relationship"
    STRONGLY_INFERRED = "Strongly Inferred Relationship"
    PROBABILISTIC_APPROXIMATE = "Probabilistic / Approximate Relationship"
    UNCERTAIN_AMBIGUOUS = "Uncertain / Ambiguous Relationship"
    NO_SUPPORTED_RELATIONSHIP = "No Supported Relationship"


class ProvenanceSource(str, Enum):
    """Source of truth for relationship provenance."""

    BACKEND_SCHEMA = "BACKEND_SCHEMA"
    SCHEMA_CONSTRAINTS = "SCHEMA_CONSTRAINTS"
    INFERENCE_ENGINE = "INFERENCE_ENGINE"
    SAMPLE_DATA = "SAMPLE_DATA"
    SEMANTIC_MATCHING = "SEMANTIC_MATCHING"


class StrictSchemaModel(BaseModel):
    """Base Pydantic model with strict validation and alias population."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        protected_namespaces=(),
    )


class BackendColumnSchema(StrictSchemaModel):
    """Column definition within a backend table schema."""

    name: str = Field(min_length=1, description="Physical database column name")
    type: str | None = Field(default=None, description="Physical column data type (e.g. INT, VARCHAR)")
    primary_key: bool = Field(default=False, description="Whether this column is a primary key")
    nullable: bool = Field(default=True, description="Whether the column can contain null values")
    unique: bool = Field(default=False, description="Whether the column has a unique constraint")


class BackendTableSchema(StrictSchemaModel):
    """Table definition within a backend database schema."""

    columns: list[BackendColumnSchema] = Field(
        default_factory=list,
        description="List of column definitions in the table",
    )


class BackendRelationshipSchema(StrictSchemaModel):
    """Relationship explicitly supplied by the backend schema."""

    name: str | None = Field(default=None, description="Optional relationship identifier")
    from_table: str = Field(
        min_length=1,
        validation_alias=AliasChoices("from_table", "fromTable", "source_table", "sourceTable"),
        description="Source/from table name",
    )
    from_column: str = Field(
        min_length=1,
        validation_alias=AliasChoices("from_column", "fromColumn", "source_column", "sourceColumn"),
        description="Source/from column name",
    )
    to_table: str = Field(
        min_length=1,
        validation_alias=AliasChoices("to_table", "toTable", "target_table", "targetTable"),
        description="Target/to table name",
    )
    to_column: str = Field(
        min_length=1,
        validation_alias=AliasChoices("to_column", "toColumn", "target_column", "targetColumn"),
        description="Target/to column name",
    )
    cardinality: str = Field(
        default="1:N",
        description="Relationship cardinality (e.g. 1:1, 1:N, N:1, N:N)",
    )
    relationship_type: str = Field(
        default="foreign_key",
        validation_alias=AliasChoices("relationship_type", "relationshipType", "type"),
        description="Relationship semantic type",
    )
    security_propagation: str | None = Field(
        default=None,
        validation_alias=AliasChoices("security_propagation", "securityPropagation"),
        description="Row-level security propagation mode",
    )
    predicate_equivalence: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("predicate_equivalence", "predicateEquivalence"),
        description="Predicate equivalence configuration",
    )


    @field_validator("cardinality")
    @classmethod
    def validate_cardinality_format(cls, value: str) -> str:
        canonical_map = {
            "1:1": "1:1",
            "one_to_one": "1:1",
            "1:n": "1:N",
            "1:N": "1:N",
            "one_to_many": "1:N",
            "n:1": "N:1",
            "N:1": "N:1",
            "many_to_one": "N:1",
            "n:n": "N:N",
            "N:N": "N:N",
            "many_to_many": "N:N",
            "unknown": "unknown",
        }
        normalized = value.strip().casefold()
        for k, v in canonical_map.items():
            if k.casefold() == normalized:
                return v
        return value.strip()


class BackendDatabaseSchema(StrictSchemaModel):
    """Complete backend schema input payload."""

    version: str = Field(default="1.0", description="Schema version identifier")
    database: str = Field(min_length=1, description="Authoritative database name")
    source: str | None = Field(default=None, description="Source engine (e.g. sqlserver)")
    tables: dict[str, BackendTableSchema] = Field(
        min_length=1,
        description="Map of table names to table definitions",
    )
    relationships: list[BackendRelationshipSchema] = Field(
        default_factory=list,
        description="Explicit backend-supplied relationships",
    )


# ---------------------------------------------------------------------------
# Internal Normalized & Output Representations
# ---------------------------------------------------------------------------

class NormalizedColumn(StrictSchemaModel):
    """Internal normalized column metadata."""

    original_name: str
    normalized_name: str
    data_type: str | None = None
    is_primary_key: bool = False
    nullable: bool = True
    unique: bool = False


class NormalizedTable(StrictSchemaModel):
    """Internal normalized table metadata."""

    original_name: str
    normalized_name: str
    columns: dict[str, NormalizedColumn]  # keyed by original_name


class NormalizedSchema(StrictSchemaModel):
    """Internal normalized database schema preserving physical names."""

    database: str
    version: str
    source: str | None = None
    tables: dict[str, NormalizedTable]  # keyed by original_name


class EvidenceBreakdown(StrictSchemaModel):
    """Detailed evidence metrics used for relationship scoring and audit."""

    name_similarity: float = 0.0
    normalized_similarity: float = 0.0
    type_compatibility: float = 0.0
    pk_signal: float = 0.0
    fk_naming_pattern: float = 0.0
    sample_overlap: float | None = None
    sample_containment: float | None = None
    sample_uniqueness: float | None = None
    semantic_similarity: float = 0.0
    explanations: list[str] = Field(default_factory=list)


class ScoringConfig(StrictSchemaModel):
    """Configurable scoring weights, multipliers, and decision thresholds."""

    # Weights when sample data is absent (sums to 1.0)
    weight_name_similarity: float = 0.20
    weight_normalized_similarity: float = 0.20
    weight_type_compatibility: float = 0.20
    weight_pk_signal: float = 0.20
    weight_fk_naming_pattern: float = 0.15
    weight_semantic_similarity: float = 0.05

    # Weights when sample data is present (sums to 1.0)
    weight_with_sample_name_similarity: float = 0.15
    weight_with_sample_normalized_similarity: float = 0.15
    weight_with_sample_type_compatibility: float = 0.15
    weight_with_sample_pk_signal: float = 0.15
    weight_with_sample_fk_naming_pattern: float = 0.10
    weight_with_sample_overlap: float = 0.15
    weight_with_sample_containment: float = 0.10
    weight_with_sample_semantic_similarity: float = 0.05

    # Decision thresholds
    strong_inference_threshold: float = 0.75
    probabilistic_threshold: float = 0.50
    uncertain_ambiguity_margin: float = 0.05
    allow_executable_inferred: bool = True


class ProcessedRelationship(StrictSchemaModel):
    """Final canonical relationship entity matching the specification."""

    id: str
    name: str
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    status: RelationshipStatus
    relationship_case: RelationshipCase
    relationship_type: str = "foreign_key"
    cardinality: str = "1:N"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: EvidenceBreakdown
    inference_method: str
    provenance: dict[str, Any]
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = "1.0"
    is_executable: bool = True

    def to_output_dict(self) -> dict[str, Any]:
        """Convert to the standard external JSON format."""
        return {
            "id": self.id,
            "name": self.name,
            "source": {
                "table": self.source_table,
                "column": self.source_column,
            },
            "target": {
                "table": self.target_table,
                "column": self.target_column,
            },
            # Compatibility flat aliases for downstream code
            "from_table": self.source_table,
            "from_column": self.source_column,
            "to_table": self.target_table,
            "to_column": self.target_column,
            "status": self.status.value,
            "relationship_case": self.relationship_case.value,
            "relationship_type": self.relationship_type,
            "cardinality": self.cardinality,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence.model_dump(),
            "inference_method": self.inference_method,
            "provenance": self.provenance,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
            "is_executable": self.is_executable,
        }


class DisconnectedComponent(StrictSchemaModel):
    """Component graph analysis result."""

    component_id: int
    tables: list[str]
    is_isolated_table: bool
    is_main_component: bool


class DisconnectedAnalysisResult(StrictSchemaModel):
    """Overall connected vs disconnected component breakdown."""

    connected_entities: list[str] = Field(default_factory=list)
    disconnected_entities: list[str] = Field(default_factory=list)
    disconnected_components: list[DisconnectedComponent] = Field(default_factory=list)
    total_tables: int = 0
    connected_components_count: int = 0
