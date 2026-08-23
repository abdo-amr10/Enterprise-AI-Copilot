"""Ownership-boundary tests for Backend-driven Semantic Layer processing."""

from __future__ import annotations

import ast
import inspect
from unittest.mock import Mock

from src.api import generation_validation_dependencies
from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.pipelines.semantic_layer.semantic_layer_generation_pipeline import (
    SemanticLayerGenerationPipeline,
)
from src.application.pipelines.semantic_layer.semantic_layer_validation_pipeline import (
    SemanticLayerValidationPipeline,
)
from src.application.services.semantic_layer.merge.semantic_layer_merger_service import (
    SemanticLayerMergeService,
)
from src.application.services.semantic_layer.semantic_layer_identity_service import (
    SemanticLayerIdentityService,
)
from src.application.services.semantic_layer.semantic_layer_metadata_generator import (
    SemanticLayerMetadataService,
)
from src.application.services.semantic_layer.validation.semantic_layer_validator import (
    SemanticLayerValidator,
)


def _draft() -> dict:
    return {
        "metadata": {
            "semantic_layer_id": "SL-001",
            "revision_id": "REV-001",
            "base_revision_id": None,
            "trigger_type": "FullRebuild",
            "status": "initial_draft",
            "validated": False,
            "human_review_required": True,
        },
        "entities": [], "relationships": [], "measures": [], "dimensions": [],
        "business_rules": [], "validation_issues": [],
    }


def test_generation_and_validation_dependency_module_has_no_local_state_adapters():
    tree = ast.parse(inspect.getsource(generation_validation_dependencies))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    forbidden = {
        "src.infrastructure.semantic_layer.retrieval.file_semantic_repository",
        "src.infrastructure.semantic_layer.retrieval.vector_store",
        "src.infrastructure.semantic_layer.ingestion.database_schema_provider",
        "src.application.services.text_to_sql.reference_data_preflight",
    }
    assert not imported_modules & forbidden


def test_generation_pipeline_processes_request_data_without_filesystem_access(monkeypatch):
    build_service = Mock()
    build_service.build.return_value = SemanticLayerBuildResponse(
        semantic_layer={**_draft(), "metadata": {}}
    )
    pipeline = SemanticLayerGenerationPipeline(
        build_service=build_service,
        merge_service=SemanticLayerMergeService(),
        metadata_service=SemanticLayerMetadataService(),
        identity_service=SemanticLayerIdentityService(),
    )
    monkeypatch.setattr(
        "pathlib.Path.open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("file I/O")),
    )
    result = pipeline.run(
        SemanticLayerGenerationRequest(
            trigger_type="FullRebuild",
            source_file_ids={"schema": "file-schema"},
            semantic_layer_id="SL-001",
        ),
        sources={"schema": {}, "relationships": []},
    )
    assert result["metadata"]["semantic_layer_id"] == "SL-001"


def test_validation_pipeline_processes_request_data_without_filesystem_access(monkeypatch):
    pipeline = SemanticLayerValidationPipeline(
        validator=SemanticLayerValidator(), auto_fixer=Mock(), max_fix_attempts=0
    )
    monkeypatch.setattr(
        "pathlib.Path.open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("file I/O")),
    )
    result, validation = pipeline.run(
        draft=_draft(), schema={"tables": {}}, relationships=[]
    )
    assert validation["status"] == "passed"
    assert result["metadata"]["status"] == "validated"
