from typing import Any

from src.application.services.semantic_layer.review_manager import (
    HumanReviewManager,
)


class SemanticLayerReviewPipeline:
    """Apply the human review decision to a validated draft."""

    def __init__(
        self,
        review_manager: HumanReviewManager,
    ) -> None:
        self._review_manager = review_manager

    def run(
        self,
        draft: dict[str, Any],
        validation: dict[str, Any],
        *,
        decision: str,
        reviewer: str,
        comments: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Returns (reviewed_draft, review_result).

        Return type fixed to a tuple -- HumanReviewManager.review()
        has always returned a (draft, review_result) tuple, but this
        pipeline was previously typed as returning a single dict.
        """

        return self._review_manager.review(
            draft=draft,
            validation=validation,
            decision=decision,
            reviewer=reviewer,
            comments=comments,
        )
