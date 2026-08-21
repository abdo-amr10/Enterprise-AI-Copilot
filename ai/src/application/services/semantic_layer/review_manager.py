"""Human approval workflow for Semantic Layer revisions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class HumanReviewManager:
    """Apply a human approval or rejection decision."""

    ALLOWED_DECISIONS = {"approve", "reject"}

    def review(
        self,
        draft: dict[str, Any],
        validation: dict[str, Any],
        *,
        decision: str,
        reviewer: str,
        comments: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Apply human review to a validated Semantic Layer draft."""

        decision = decision.lower().strip()

        if decision not in self.ALLOWED_DECISIONS:
            raise ValueError(
                "decision must be 'approve' or 'reject'."
            )

        if not reviewer.strip():
            raise ValueError("reviewer cannot be empty.")

        if decision == "reject" and not comments.strip():
            raise ValueError(
                "comments are required when rejecting a revision."
            )

        validation_status = validation.get("status")

        if decision == "approve" and validation_status != "passed":
            raise ValueError(
                "A semantic layer can only be approved "
                "after successful validation."
            )

        metadata = draft.get("metadata", {})

        if not isinstance(metadata, dict):
            raise ValueError("Semantic Layer metadata is required for human review.")

        semantic_layer_id = metadata.get("semantic_layer_id")
        revision_id = metadata.get("revision_id")

        if not semantic_layer_id:
            raise ValueError(
                "semantic_layer_id is required for human review."
            )

        if not revision_id:
            raise ValueError(
                "revision_id is required for human review."
            )

        timestamp = datetime.now(timezone.utc).isoformat()

        review_result = {
            "decision": decision,
            "reviewer": reviewer,
            "comments": comments.strip(),
            "reviewed_at": timestamp,
            "validation_status_at_review": validation_status,
        }

        reviewed_draft = deepcopy(draft)

        metadata = reviewed_draft.setdefault("metadata", {})

        metadata.update(
            {
                "status": (
                    "approved"
                    if decision == "approve"
                    else "rejected"
                ),
                "validated": validation_status == "passed",
                "human_review_required": decision != "approve",
                "review": review_result,
            }
        )

        return reviewed_draft, review_result
