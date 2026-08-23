"""Lifecycle tests for Backend-owned Semantic Layer revisions."""

from copy import deepcopy

import numpy as np
import pytest

from src.application.pipelines.semantic_layer.semantic_layer_embedding_pipeline import (
    SemanticLayerEmbeddingPipeline,
)
from src.application.pipelines.semantic_layer.semantic_layer_review_pipeline import (
    SemanticLayerReviewPipeline,
)
from src.application.pipelines.semantic_layer.semantic_layer_validation_pipeline import (
    SemanticLayerValidationPipeline,
)
from src.application.services.semantic_layer.review_manager import HumanReviewManager
from src.application.services.semantic_layer.validation.semantic_layer_validator import (
    SemanticLayerValidator,
)
from src.infrastructure.semantic_layer.retrieval.semantic_index_builder import (
    SemanticIndexBuilder,
)


SCHEMA = {"tables": {"customers": {"columns": [{"name": "id"}]}}}


def _draft() -> dict:
    return {
        "metadata": {
            "semantic_layer_id": "SL-101",
            "revision_id": "REV-101",
            "base_revision_id": "REV-100",
            "trigger_type": "Incremental",
            "status": "initial_draft",
            "validated": False,
            "human_review_required": True,
        },
        "entities": [{"object_id": "obj-customer", "name": "Customer", "mapping": "customers"}],
        "relationships": [], "measures": [], "dimensions": [],
        "business_rules": [], "validation_issues": [],
    }


class _Fixer:
    def __init__(self):
        self.calls = 0

    def fix(self, draft, validation, schema, relationships):
        self.calls += 1
        fixed = deepcopy(draft)
        fixed["entities"][0]["mapping"] = "customers"
        return fixed


class _Embedding:
    model_name = "test-model"
    model_version = "test-version"
    embedding_dimension = 2

    def encode_documents(self, texts):
        return np.array([[1.0, 0.0] for _ in texts], dtype=np.float32)


class _Index:
    def build(self, documents, embeddings, metadata):
        self.metadata = metadata

    def save(self):
        pass


def test_rejected_manual_edit_is_completely_revalidated_before_approval_and_indexing():
    validation = SemanticLayerValidationPipeline(
        validator=SemanticLayerValidator(), auto_fixer=_Fixer(), max_fix_attempts=1
    )
    review = SemanticLayerReviewPipeline(HumanReviewManager())

    first_draft, first_result = validation.run(_draft(), SCHEMA, [])
    assert first_result["status"] == "passed"
    rejected, rejection = review.run(
        first_draft, first_result, decision="Reject", reviewer="admin", comments="Needs review"
    )
    assert rejection["decision"] == "reject"
    assert rejected["metadata"]["status"] == "rejected"

    # Backend/Admin edit simulation: the same persisted revision is submitted
    # back to the same complete validation pipeline with a schema mismatch.
    manually_edited = deepcopy(rejected)
    manually_edited["metadata"]["status"] = "initial_draft"
    manually_edited["entities"][0]["mapping"] = "missing_table"
    final_draft, final_result = validation.run(manually_edited, SCHEMA, [])
    assert final_result["status"] == "passed"
    assert final_draft["entities"][0]["mapping"] == "customers"
    assert final_draft["metadata"]["revision_id"] == "REV-101"

    approved, approval = review.run(
        final_draft, final_result, decision="Approve", reviewer="admin"
    )
    assert approval["decision"] == "approve"
    assert approved["metadata"]["status"] == "approved"

    index = _Index()
    SemanticLayerEmbeddingPipeline(SemanticIndexBuilder(_Embedding(), index)).run(approved)
    assert index.metadata["revision_id"] == "REV-101"


def test_rejection_loop_can_repeat_and_never_indexes_a_rejected_revision():
    validation = SemanticLayerValidationPipeline(
        validator=SemanticLayerValidator(), auto_fixer=_Fixer(), max_fix_attempts=1
    )
    review = SemanticLayerReviewPipeline(HumanReviewManager())
    validated, result = validation.run(_draft(), SCHEMA, [])
    rejected, _ = review.run(validated, result, decision="Reject", reviewer="admin", comments="First pass")
    revalidated, rerun_result = validation.run(rejected, SCHEMA, [])
    rejected_again, _ = review.run(
        revalidated, rerun_result, decision="Reject", reviewer="admin", comments="Second pass"
    )
    with pytest.raises(ValueError, match="approved"):
        SemanticLayerEmbeddingPipeline(SemanticIndexBuilder(_Embedding(), _Index())).run(rejected_again)
