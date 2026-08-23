"""Composition root for processing-only Semantic Layer human review."""

from src.application.pipelines.semantic_layer.semantic_layer_review_pipeline import (
    SemanticLayerReviewPipeline,
)
from src.application.services.semantic_layer.review_manager import HumanReviewManager


_semantic_review_pipeline: SemanticLayerReviewPipeline | None = None


def get_semantic_review_pipeline() -> SemanticLayerReviewPipeline:
    """Build the in-memory review transformation pipeline."""

    global _semantic_review_pipeline
    if _semantic_review_pipeline is None:
        _semantic_review_pipeline = SemanticLayerReviewPipeline(
            HumanReviewManager()
        )
    return _semantic_review_pipeline
