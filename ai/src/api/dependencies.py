"""Composition root for Backend-authoritative retrieval and Text-to-SQL."""

from __future__ import annotations


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
from src.infrastructure.semantic_layer.retrieval.backend_semantic_repository import BackendSemanticRepository
from src.infrastructure.semantic_layer.ingestion.backend_database_schema_provider import BackendDatabaseSchemaProvider

_SETTINGS = SemanticSettings()
_SELF_CORRECTION_SETTINGS = SelfCorrectionSettings()

# --------------------------------------------------------------------------
# Singletons. Built once per process: the embedding model, the vector
# index, and the physical schema file are all comparatively expensive
# or pointless to reload per request.
# --------------------------------------------------------------------------

_semantic_repository: BackendSemanticRepository | None = None
_context_retrieval_service: ContextRetrievalService | None = None
_self_correction_service: SelfCorrectionService | None = None


def get_semantic_repository() -> BackendSemanticRepository:
    global _semantic_repository
    if _semantic_repository is None:
        _semantic_repository = BackendSemanticRepository()
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
    )


def get_semantic_retrieval_pipeline() -> SemanticRetrievalPipeline:
    return SemanticRetrievalPipeline(retrieval_service=get_context_service())


# End of local-state composition root.
