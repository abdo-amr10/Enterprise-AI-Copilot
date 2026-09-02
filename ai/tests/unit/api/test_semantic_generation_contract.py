import pytest
from pydantic import ValidationError

from src.api.contracts import SemanticGenerateRequest
from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)


def test_full_rebuild_does_not_require_a_revision_id() -> None:
    request = SemanticGenerateRequest.model_validate(
        {
            "semanticLayerId": "sl-001",
            "triggerType": "FullRebuild",
            "sourceFileIds": {"schema": "file-001"},
        }
    )

    assert request.semanticLayerId == "sl-001"
    assert request.sourceFileIds == {"schema": "file-001"}


def test_generation_accepts_null_optional_source_file_ids() -> None:
    request = SemanticGenerateRequest.model_validate(
        {
            "semanticLayerId": "sl-001",
            "triggerType": "FullRebuild",
            "sourceFileIds": {
                "schema": "file-001",
                "documentation": None,
                "glossary": None,
                "sampleData": None,
            },
        }
    )

    assert request.sourceFileIds["schema"] == "file-001"
    assert request.sourceFileIds["documentation"] is None


def test_generation_rejects_null_schema_file_id_downstream() -> None:
    request = SemanticGenerateRequest.model_validate(
        {
            "semanticLayerId": "sl-001",
            "triggerType": "FullRebuild",
            "sourceFileIds": {"schema": None},
        }
    )

    with pytest.raises(ValueError, match="source_file_ids.schema is required"):
        SemanticLayerGenerationRequest(
            trigger_type=request.triggerType,
            semantic_layer_id=request.semanticLayerId,
            source_file_ids={
                key: value for key, value in request.sourceFileIds.items()
                if value is not None
            },
        )


def test_generation_accepts_null_affected_objects() -> None:
    request = SemanticGenerateRequest.model_validate(
        {
            "semanticLayerId": "sl-001",
            "triggerType": "FullRebuild",
            "sourceFileIds": {"schema": "file-001"},
            "affectedObjects": None,
        }
    )

    assert request.affectedObjects is None

