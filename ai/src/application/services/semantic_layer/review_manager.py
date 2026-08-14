"""Human approval workflow for semantic-layer drafts."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class AIDataReviewManager:
    """Apply an explicit human decision and persist review metadata."""
       
    ALLOWED_DECISIONS = {"approve", "reject"}
     

    def review(self, draft: dict[str, Any], validation: dict[str, Any], *, decision: str, reviewer: str, comments: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Apply a human review decision to a semantic-layer draft.
        Approval is allowed only when validation has passed.
        Rejected drafts keep the reviewer comments for later correction
        and re-validation.

        Args:
            draft: Semantic-layer draft being reviewed.
            validation: Result produced by the automated semantic-layer
                validation step.
            decision: Human review decision. Must be ``"approve"`` or
                ``"reject"``.
            reviewer: Identifier or name of the person performing the review.
            comments: Optional reviewer feedback explaining the decision
                or required corrections.

        Returns:
            A tuple containing:
            - The reviewed semantic-layer draft with updated review metadata.
            - The review result containing the decision, reviewer, comments,
              timestamp, and validation status at the time of review.

        Raises:
            ValueError: If the decision is not ``"approve"`` or ``"reject"``.
            ValueError: If approval is requested before validation passes.
        """

        decision = decision.lower().strip()
        if decision not in self.ALLOWED_DECISIONS:
            raise ValueError("decision must be 'approve' or 'reject'")
        
        validation_status = validation.get("status")

        if decision == "approve" and validation_status != "passed":
            raise ValueError("A semantic layer can only be approved "
                              "after successful validation.")

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

        metadata.update({
            "status": ("approved" if decision == "approve" else "rejected"),
            "validated": validation_status == "passed",
            "human_review_required": decision != "approve",
            "review": review_result,
        })

        return reviewed_draft, review_result
