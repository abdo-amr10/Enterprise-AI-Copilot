"""Build a fresh, local approved Semantic Layer with the real AI pipeline."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from src.api.generation_validation_dependencies import (
    get_semantic_generation_pipeline,
    get_semantic_validation_pipeline,
)
from src.api.semantic_review_dependencies import get_semantic_review_pipeline
from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)
from src.application.pipelines.semantic_layer.semantic_layer_embedding_pipeline import (
    SemanticLayerEmbeddingPipeline,
)
from src.application.services.semantic_layer.semantic_layer_metadata_generator import (
    SemanticLayerMetadataService,
)
from src.config.semantic_settings import SemanticSettings
from src.infrastructure.semantic_layer.retrieval.embedding_service import EmbeddingService
from src.infrastructure.semantic_layer.retrieval.faiss_vector_index import FaissVectorIndex
from src.infrastructure.semantic_layer.retrieval.semantic_index_builder import SemanticIndexBuilder

from .conftest import REPOSITORY_ROOT, save_json


pytestmark = pytest.mark.integration


def _documented_sources() -> tuple[dict, dict, list[dict]]:
    """Load the repository's documented schema inputs without copying them."""

    metadata_dir = REPOSITORY_ROOT / "docs" / "database_metadata"
    schema = json.loads((metadata_dir / "schema.json").read_text(encoding="utf-8"))
    sources = {
        "schema": schema,
        "relationships": schema["relationships"],
        "documentation": (metadata_dir / "documentation.md").read_text(encoding="utf-8"),
        "business_glossary": (metadata_dir / "business_glossary.md").read_text(encoding="utf-8"),
        "sample_data": json.loads((metadata_dir / "sample_data.json").read_text(encoding="utf-8")),
    }
    return sources, schema, schema["relationships"]


def _configure_live_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep this real 12k-token generation independent of shell defaults."""

    timeout = os.environ.get("EAI_LIVE_OLLAMA_TIMEOUT_SECONDS", "900")
    try:
        if float(timeout) <= 0:
            raise ValueError
    except ValueError as error:
        raise pytest.UsageError("EAI_LIVE_OLLAMA_TIMEOUT_SECONDS must be positive.") from error
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", timeout)


def test_real_semantic_layer_generation_validation_review_and_indexing(
    artifact_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Create fresh approved JSON and FAISS artifacts using real Ollama/BGE-M3."""

    _configure_live_timeout(monkeypatch)
    sources, schema, relationships = _documented_sources()
    semantic_layer_id = f"live-semantic-layer-{uuid4()}"
    revision_id = f"live-semantic-revision-{uuid4()}"
    request = SemanticLayerGenerationRequest(
        trigger_type="FullRebuild",
        semantic_layer_id=semantic_layer_id,
        source_file_ids={
            "schema": "docs/database_metadata/schema.json",
            "documentation": "docs/database_metadata/documentation.md",
            "glossary": "docs/database_metadata/business_glossary.md",
            "sampleData": "docs/database_metadata/sample_data.json",
        },
    )
    save_json(artifact_dir, "generation_request.json", {
        "triggerType": request.trigger_type,
        "semanticLayerId": request.semantic_layer_id,
        "sourceFileIds": request.source_file_ids,
        "localRevisionId": revision_id,
    })

    generated = get_semantic_generation_pipeline().run(request=request, sources=sources)
    generated = SemanticLayerMetadataService().initialize(generated, semantic_layer_id, revision_id)
    generated_path = save_json(artifact_dir, "generated_semantic_layer.json", generated)

    validated, validation = get_semantic_validation_pipeline().run(generated, schema, relationships)
    validation_path = save_json(artifact_dir, "validation_result.json", validation)
    save_json(artifact_dir, "validated_semantic_layer.json", validated)
    assert validation["status"] == "passed", validation

    approved, review = get_semantic_review_pipeline().run(
        draft=validated,
        validation=validation,
        decision="Approve",
        reviewer="live-semantic-layer-test",
        comments="",
    )
    review_path = save_json(artifact_dir, "review_result.json", review)
    approved_path = save_json(artifact_dir, "approved_semantic_layer.json", approved)
    assert approved["metadata"]["status"] == "approved"

    settings = SemanticSettings()
    index_path = artifact_dir / settings.vector_index_filename
    embedding_service = EmbeddingService(
        settings.production_embedding_model_path,
        model_name=settings.production_embedding_model_name,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        normalize=settings.normalize_embeddings,
    )
    index_result = SemanticLayerEmbeddingPipeline(
        SemanticIndexBuilder(embedding_service, FaissVectorIndex(index_path), settings=settings)
    ).run(approved)
    index_result["index_path"] = str(index_path)
    index_result_path = save_json(artifact_dir, "index_build_result.json", index_result)
    assert index_path.is_file()
    assert index_path.with_suffix(index_path.suffix + ".metadata.json").is_file()

    print("\n" + "=" * 60)
    print("SEMANTIC LAYER LIVE TEST RESULT")
    print("=" * 60)
    print("Status: SUCCESS")
    print(f"Generated Semantic Layer: {generated_path}")
    print(f"Validation Result: {validation_path}")
    print(f"Review Result: {review_path}")
    print(f"Approved Semantic Layer: {approved_path}")
    print(f"Semantic Index: {index_path}")
    print(f"Index Build Result: {index_result_path}")
    print(f"Artifact Directory: {artifact_dir}")
