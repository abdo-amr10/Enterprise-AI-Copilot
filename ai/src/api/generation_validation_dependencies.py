"""Composition root for processing-only Semantic Layer endpoints.

The generation and validation endpoints receive all source content and drafts
from Backend request bodies.  This module must not import filesystem-backed
retrieval, indexing, schema, sample-data, or persistence adapters.
"""

from src.application.pipelines.semantic_layer.semantic_layer_generation_pipeline import (
    SemanticLayerGenerationPipeline,
)
from src.application.pipelines.semantic_layer.semantic_layer_validation_pipeline import (
    SemanticLayerValidationPipeline,
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
from src.infrastructure.llm.model_config import SEMANTIC_LAYER_CONFIG
from src.infrastructure.llm.ollama_client import OllamaClient


_semantic_generation_pipeline: SemanticLayerGenerationPipeline | None = None
_semantic_validation_pipeline: SemanticLayerValidationPipeline | None = None


def get_semantic_generation_pipeline() -> SemanticLayerGenerationPipeline:
    """Build the Backend-driven, in-memory draft-generation pipeline."""

    global _semantic_generation_pipeline
    if _semantic_generation_pipeline is None:
        llm_client = OllamaClient(config=SEMANTIC_LAYER_CONFIG)
        build_service = SemanticLayerBuildService(
            full_rebuild_strategy=FullRebuildStrategy(FullRebuildBuilder(llm_client)),
            incremental_strategy=IncrementalBuildStrategy(IncrementalBuilder(llm_client)),
        )
        _semantic_generation_pipeline = SemanticLayerGenerationPipeline(
            build_service=build_service,
            merge_service=SemanticLayerMergeService(),
            metadata_service=SemanticLayerMetadataService(),
            identity_service=SemanticLayerIdentityService(),
        )
    return _semantic_generation_pipeline


def get_semantic_validation_pipeline() -> SemanticLayerValidationPipeline:
    """Build the Backend-driven, in-memory validation pipeline."""

    global _semantic_validation_pipeline
    if _semantic_validation_pipeline is None:
        llm_client = OllamaClient(config=SEMANTIC_LAYER_CONFIG)
        _semantic_validation_pipeline = SemanticLayerValidationPipeline(
            validator=SemanticLayerValidator(),
            auto_fixer=SemanticLayerAutoFixer(llm_client),
            max_fix_attempts=2,
        )
    return _semantic_validation_pipeline
