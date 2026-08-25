"""Composition root for Backend-authoritative retrieval and Text-to-SQL.

``AI_LOCAL_DEV_MODE=true`` enables explicit offline development artifacts.
The default remains Backend-authoritative runtime wiring.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.application.pipelines.context_retrieval.semantic_retrieval_pipeline import (
    SemanticRetrievalPipeline,
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
from src.application.services.self_correction.validators.sql_rls_validator import SQLRlsValidator
from src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)
from src.application.services.text_to_sql.sql_generation_service import (
    SQLGenerationService,
)
from src.application.services.text_to_sql.text_to_sql_pipeline import TextToSQLPipeline
from src.config.self_correction_settings import SelfCorrectionSettings
from src.config.semantic_settings import SemanticSettings
from src.infrastructure.llm.model_config import (
    QWEN_CONFIG,
    SQL_CORRECTION_CONFIG,
    SQL_CRITIC_CONFIG,
)
from src.infrastructure.llm.ollama_client import OllamaClient
from src.infrastructure.semantic_layer.ingestion.database_schema_provider import (
    DatabaseSchemaProvider,
)
from src.infrastructure.semantic_layer.retrieval.backend_semantic_repository import BackendSemanticRepository
from src.infrastructure.semantic_layer.retrieval.embedding_service import EmbeddingService
from src.infrastructure.semantic_layer.retrieval.faiss_vector_index import FaissVectorIndex
from src.infrastructure.semantic_layer.ingestion.backend_database_schema_provider import BackendDatabaseSchemaProvider
from src.infrastructure.semantic_layer.retrieval.file_semantic_repository import (
    FileSemanticRepository,
)

_SETTINGS = SemanticSettings()
_SELF_CORRECTION_SETTINGS = SelfCorrectionSettings()
_AI_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _AI_ROOT.parent
_LOCAL_APPROVED_LAYER = _AI_ROOT / "outputs" / "semantic_layer" / "approved_semantic_layer.json"
_LOCAL_SCHEMA = _REPO_ROOT / "docs" / "database_metadata" / "schema.json"

# --------------------------------------------------------------------------
# Singletons. Built once per process: the embedding model, the vector
# index, and the physical schema file are all comparatively expensive
# or pointless to reload per request.
# --------------------------------------------------------------------------

_semantic_repository: BackendSemanticRepository | FileSemanticRepository | None = None
_context_retrieval_service: ContextRetrievalService | None = None
_self_correction_service: SelfCorrectionService | None = None


def is_local_development_mode() -> bool:
    """Return whether explicit offline development mode is enabled."""

    return os.getenv("AI_LOCAL_DEV_MODE", "").casefold() == "true"


def get_semantic_repository() -> BackendSemanticRepository | FileSemanticRepository:
    global _semantic_repository
    if _semantic_repository is None:
        embedding_service = EmbeddingService(
            _SETTINGS.production_embedding_model_path,
            model_name=_SETTINGS.production_embedding_model_name,
            device=_SETTINGS.embedding_device,
            batch_size=_SETTINGS.embedding_batch_size,
            normalize=_SETTINGS.normalize_embeddings,
        )
        _semantic_repository = (
            FileSemanticRepository(
                _LOCAL_APPROVED_LAYER,
                embedding_service=embedding_service,
                vector_store=FaissVectorIndex(
                    _AI_ROOT / "outputs" / "semantic_layer" / _SETTINGS.vector_index_filename
                ),
            )
            if is_local_development_mode()
            else BackendSemanticRepository(
                embedding_service=embedding_service,
                vector_index=FaissVectorIndex(),
                settings=_SETTINGS,
            )
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


def get_schema_provider():
    if is_local_development_mode():
        return DatabaseSchemaProvider(_LOCAL_SCHEMA)
    return BackendDatabaseSchemaProvider()


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
        rls_validator = SQLRlsValidator(
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
            rls_validator=rls_validator,
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
    )


def get_semantic_retrieval_pipeline() -> SemanticRetrievalPipeline:
    return SemanticRetrievalPipeline(retrieval_service=get_context_service())


# End of local-state composition root.
