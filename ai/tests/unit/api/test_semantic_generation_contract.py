import pytest
from pydantic import ValidationError

from src.api.contracts import SemanticGenerateRequest


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


def test_generation_rejects_null_source_file_ids() -> None:
    with pytest.raises(ValidationError):
        SemanticGenerateRequest.model_validate(
            {
                "semanticLayerId": "sl-001",
                "triggerType": "FullRebuild",
                "sourceFileIds": {"schema": None},
            }
        )
