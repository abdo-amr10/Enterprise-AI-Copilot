from datetime import datetime

import pytest

from src.application.services.semantic_layer.review_manager import HumanReviewManager


def _draft():
    return {
        "metadata": {
            "semantic_layer_id": "SL-001",
            "revision_id": "REV-001",
            "trigger_type": "Incremental",
            "base_revision_id": "REV-000",
            "status": "validated",
            "validated": True,
            "human_review_required": True,
        }
    }


def test_approval_requires_successful_validation_and_preserves_identity():
    manager = HumanReviewManager()
    with pytest.raises(ValueError, match="only be approved"):
        manager.review(_draft(), {"status": "failed"}, decision="Approve", reviewer="u1")
    reviewed, result = manager.review(
        _draft(), {"status": "passed"}, decision="Approve", reviewer="u1", comments="Looks good"
    )
    assert result["decision"] == "approve"
    assert isinstance(datetime.fromisoformat(result["reviewed_at"]), datetime)
    assert reviewed["metadata"]["status"] == "approved"
    assert reviewed["metadata"]["semantic_layer_id"] == "SL-001"
    assert reviewed["metadata"]["revision_id"] == "REV-001"
    assert reviewed["metadata"]["trigger_type"] == "Incremental"


def test_rejection_requires_comments_and_is_processing_only(monkeypatch):
    manager = HumanReviewManager()
    with pytest.raises(ValueError, match="comments are required"):
        manager.review(_draft(), {"status": "passed"}, decision="Reject", reviewer="u1")
    monkeypatch.setattr(
        "pathlib.Path.open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("file I/O")),
    )
    reviewed, result = manager.review(
        _draft(), {"status": "passed"}, decision="Reject", reviewer="u1", comments="Needs mapping"
    )
    assert result["decision"] == "reject"
    assert result["comments"] == "Needs mapping"
    assert reviewed["metadata"]["status"] == "rejected"
    assert reviewed["metadata"]["human_review_required"] is True
