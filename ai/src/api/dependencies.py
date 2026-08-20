"""Composition root for the AI runtime API.

This module is the only place that constructs concrete infrastructure
objects and wires them into application services. Nothing here
reimplements logic that already exists elsewhere in src/ -- it only
assembles the existing pieces (and the new Self-Correction pieces)
into the two pipelines exposed over HTTP.
"""

from __future__ import annotations

from pathlib import Path

from src.application.pipelines.context_retrieval.semantic_retrieval_pipeline import (
    SemanticRetrievalPipeline,
)
from src.application.pipelines.semantic_layer.semantic_layer_generation_pipeline import (
    SemanticLayerGenerationPipeline,
)
from src.application.pipelines.semantic_layer.semantic_layer_review_pipeline import (
    SemanticLayerReviewPipeline,
)
from src.application.pipelines.semantic_layer.semantic_layer_validation_pipeline import (
    SemanticLayerValidationPipeline,
)
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import (
    CopilotRuntimePipeline,
)
from src.application.services.self_correction.critic_finding_verifier import (
    CriticFindingVerifier,
)
from src.application.services.self_correction.self_correction_service import (
    SelfCorrectionService,
)
from src.application.services.self_correction.sql_correction_service import SQLCorrectionService
from src.application.services.self_correction.sql_critic_service import SQLCriticService
from src.application.services.self_correction.validators.sql_relationship_validator import (
    SQLRelationshipValidator,
)
from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)
from src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)
from src.application.services.semantic_layer.builders.full_build_builder import (
    FullRebuildBuilder,
)
from src.application.services.semantic_layer.builders.incremental_builder import (
    IncrementalBuilder,
)
from src.application.services.semantic_layer.merge.semantic_layer_merger_service import (
    SemanticLayerMergeService,
)
from src.application.services.semantic_layer.review_manager import HumanReviewManager
from src.application.services.semantic_layer.semantic_layer_build_service import (
    SemanticLayerBuildService,
)
from src.application.services.semantic_layer.semantic_layer_identity_service import (
    SemanticLayerIdentityService,
)
from src.application.services.semantic_layer.semantic_layer_metadata_generator import (
    SemanticLayerMetadataService,
)
from src.application.services.semantic_layer.strategy.full_rebuild_strategy import (
    FullRebuildStrategy,
)
from src.application.services.semantic_layer.strategy.incremental_build_strategy import (
    IncrementalBuildStrategy,
)
from src.application.services.semantic_layer.validation.semantic_layer_auto_fixer import (
    SemanticLayerAutoFixer,
)
from src.application.services.semantic_layer.validation.semantic_layer_validator import (
    SemanticLayerValidator,
)
from src.application.services.text_to_sql.sql_generation_service import (
    SQLGenerationService,
)
from src.application.services.text_to_sql.text_to_sql_pipeline import TextToSQLPipeline
from src.config.self_correction_settings import SelfCorrectionSettings
from src.config.semantic_settings import SemanticSettings
from src.infrastructure.llm.model_config import (
    QWEN_CONFIG,
    SEMANTIC_LAYER_CONFIG,
    SQL_CORRECTION_CONFIG,
    SQL_CRITIC_CONFIG,
)
from src.infrastructure.semantic_layer.persistence.semantic_layer_id_generator import (
    SemanticLayerIdGenerator,
)
from src.infrastructure.llm.ollama_client import OllamaClient
from src.infrastructure.semantic_layer.ingestion.database_schema_provider import (
    DatabaseSchemaProvider,
)
from src.infrastructure.semantic_layer.retrieval.embedding_service import (
    EmbeddingService,
)
from src.infrastructure.semantic_layer.retrieval.file_semantic_repository import (
    FileSemanticRepository,
)
from src.infrastructure.semantic_layer.retrieval.vector_store import LocalVectorStore
from src.application.services.text_to_sql.reference_data_preflight import ReferenceDataPreflight

BASE_DIR = Path(__file__).resolve().parents[2]  # .../ai
REPO_ROOT = BASE_DIR.parent  # repo root, sibling of ai/, backend/, docs/

SEMANTIC_LAYER_PATH = BASE_DIR / "outputs" / "semantic_layer" / "approved_semantic_layer.json"
DATABASE_SCHEMA_PATH = REPO_ROOT / "docs" / "database_metadata" / "schema.json"
SAMPLE_DATA_PATH = REPO_ROOT / "docs" / "database_metadata" / "sample_data.json"

_SETTINGS = SemanticSettings()
_SELF_CORRECTION_SETTINGS = SelfCorrectionSettings()

# --------------------------------------------------------------------------
# Singletons. Built once per process: the embedding model, the vector
# index, and the physical schema file are all comparatively expensive
# or pointless to reload per request.
# --------------------------------------------------------------------------

_semantic_repository: FileSemanticRepository | None = None
_context_retrieval_service: ContextRetrievalService | None = None
_schema_provider: DatabaseSchemaProvider | None = None
_self_correction_service: SelfCorrectionService | None = None
_semantic_generation_pipeline: SemanticLayerGenerationPipeline | None = None
_semantic_validation_pipeline: SemanticLayerValidationPipeline | None = None
_semantic_review_pipeline: SemanticLayerReviewPipeline | None = None


def get_semantic_repository() -> FileSemanticRepository:
    global _semantic_repository
    if _semantic_repository is None:
        embedding_service = EmbeddingService(
            model_path=_SETTINGS.embedding_model_path
        )
        vector_store = LocalVectorStore(
            SEMANTIC_LAYER_PATH.parent / _SETTINGS.vector_index_filename
        )
        _semantic_repository = FileSemanticRepository(
            semantic_layer_path=SEMANTIC_LAYER_PATH,
            embedding_service=embedding_service,
            vector_store=vector_store,
        )
    return _semantic_repository


def get_context_service() -> ContextRetrievalService:
    global _context_retrieval_service
    if _context_retrieval_service is None:
        _context_retrieval_service = ContextRetrievalService(
            semantic_repository=get_semantic_repository(),
            default_top_k=_SETTINGS.default_top_k,
        )
    return _context_retrieval_service


def get_schema_provider() -> DatabaseSchemaProvider:
    global _schema_provider
    if _schema_provider is None:
        _schema_provider = DatabaseSchemaProvider(DATABASE_SCHEMA_PATH)
    return _schema_provider


def get_self_correction_service() -> SelfCorrectionService:
    global _self_correction_service
    if _self_correction_service is None:
        syntax_validator = SQLSyntaxValidator()
        schema_validator = SQLSchemaValidator(
            schema_provider=get_schema_provider(),
            syntax_validator=syntax_validator,
        )
        relationship_validator = SQLRelationshipValidator(
            semantic_repository=get_semantic_repository(),
            syntax_validator=syntax_validator,
            schema_validator=schema_validator,
        )
        critic_service = SQLCriticService(
            llm_client=OllamaClient(config=SQL_CRITIC_CONFIG)
        )
        correction_service = SQLCorrectionService(
            llm_client=OllamaClient(config=SQL_CORRECTION_CONFIG)
        )

        _self_correction_service = SelfCorrectionService(
            context_retrieval_service=get_context_service(),
            syntax_validator=syntax_validator,
            schema_validator=schema_validator,
            relationship_validator=relationship_validator,
            critic_service=critic_service,
            finding_verifier=CriticFindingVerifier(get_schema_provider()),
            correction_service=correction_service,
            max_attempts=_SELF_CORRECTION_SETTINGS.max_attempts,
        )
    return _self_correction_service


def get_copilot_pipeline() -> CopilotRuntimePipeline:
    sql_generation_service = SQLGenerationService(
        llm_client=OllamaClient(config=QWEN_CONFIG)
    )
    text_to_sql_pipeline = TextToSQLPipeline(
        context_retrieval_service=get_context_service(),
        sql_generation_service=sql_generation_service,
    )
    return CopilotRuntimePipeline(
        text_to_sql_pipeline=text_to_sql_pipeline,
        self_correction_service=get_self_correction_service(),
        reference_data_preflight=ReferenceDataPreflight(SAMPLE_DATA_PATH),
    )


def get_semantic_retrieval_pipeline() -> SemanticRetrievalPipeline:
    return SemanticRetrievalPipeline(retrieval_service=get_context_service())


def get_semantic_generation_pipeline() -> SemanticLayerGenerationPipeline:
    """Build the AI-owned draft-generation pipeline once per process."""

    global _semantic_generation_pipeline
    if _semantic_generation_pipeline is None:
        llm_client = OllamaClient(config=SEMANTIC_LAYER_CONFIG)
        build_service = SemanticLayerBuildService(
            full_rebuild_strategy=FullRebuildStrategy(
                FullRebuildBuilder(llm_client)
            ),
            incremental_strategy=IncrementalBuildStrategy(
                IncrementalBuilder(llm_client)
            ),
        )
        _semantic_generation_pipeline = SemanticLayerGenerationPipeline(
            build_service=build_service,
            merge_service=SemanticLayerMergeService(),
            metadata_service=SemanticLayerMetadataService(
                SemanticLayerIdGenerator()
            ),
            identity_service=SemanticLayerIdentityService(),
        )
    return _semantic_generation_pipeline


def get_semantic_validation_pipeline() -> SemanticLayerValidationPipeline:
    """Build the AI-owned validation and auto-fix pipeline once per process."""

    global _semantic_validation_pipeline
    if _semantic_validation_pipeline is None:
        llm_client = OllamaClient(config=SEMANTIC_LAYER_CONFIG)
        _semantic_validation_pipeline = SemanticLayerValidationPipeline(
            validator=SemanticLayerValidator(),
            auto_fixer=SemanticLayerAutoFixer(llm_client),
            max_fix_attempts=2,
        )
    return _semantic_validation_pipeline


def get_semantic_review_pipeline() -> SemanticLayerReviewPipeline:
    """Build the AI-owned draft review transformation pipeline."""

    global _semantic_review_pipeline
    if _semantic_review_pipeline is None:
        _semantic_review_pipeline = SemanticLayerReviewPipeline(
            HumanReviewManager()
        )
    return _semantic_review_pipeline
