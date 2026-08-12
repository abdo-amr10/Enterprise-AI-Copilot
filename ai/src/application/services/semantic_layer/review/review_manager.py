"""Human approval workflow for semantic-layer drafts."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class SemanticLayerReviewManager:
    """Apply an explicit approve/reject decision and persist review metadata."""

    def review(self, draft: dict[str, Any], validation: dict[str, Any], *, decision: str, reviewer: str, comments: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
        decision = decision.lower().strip()
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be 'approve' or 'reject'")
        if decision == "approve" and validation.get("status") == "failed":
            raise ValueError("A semantic layer with validation errors cannot be approved.")

        timestamp = datetime.now(timezone.utc).isoformat()
        review_result = {
            "decision": decision,
            "reviewer": reviewer,
            "comments": comments,
            "reviewed_at": timestamp,
            "validation_status_at_review": validation.get("status"),
        }
        approved = deepcopy(draft)
        approved.setdefault("metadata", {})
        approved["metadata"].update({
            "status": "approved" if decision == "approve" else "rejected",
            "validated": validation.get("status") != "failed",
            "human_review_required": False,
            "review": review_result,
        })
        return approved, review_result
