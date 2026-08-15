import pytest

from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)


def test_generation_request_uses_named_source_file_ids() -> None:
    request = SemanticLayerGenerationRequest(
        trigger_type="FullRebuild",
        source_file_ids={
            "schema": "file-001",
            "documentation": "file-002",
            "glossary": "file-003",
        },
    )

    assert request.source_file_ids["schema"] == "file-001"


def test_generation_request_requires_schema_file_id() -> None:
    with pytest.raises(ValueError, match="schema"):
        SemanticLayerGenerationRequest(
            trigger_type="FullRebuild",
            source_file_ids={"glossary": "file-003"},
        )
