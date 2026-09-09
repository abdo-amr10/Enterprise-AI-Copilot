"""Continuation Resolver that updates structured semantic query state without SQL string mutation."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Optional

from src.application.services.conversation.followup.models import (
    FollowupConfidence,
    FollowupDetectionResult,
    FollowupType,
)
from src.application.services.conversation.state.conversation_state import (
    ConversationState,
    SemanticQueryState,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContinuationResolution:
    is_resolved: bool
    resolved_question: str
    updated_semantic_state: SemanticQueryState
    operation_applied: Optional[FollowupType] = None
    reason: Optional[str] = None


class ContinuationResolver:
    """Applies structured continuation operations to SemanticQueryState and resolves standalone query."""

    _MONTHS_YEARS_REGEX = re.compile(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december|\d{4}|last\s+year|last\s+month|q[1-4])\b",
        re.IGNORECASE,
    )

    _TOP_N_REGEX = re.compile(r"\b(?:top|first)\s+(\d+)\b", re.IGNORECASE)
    _YEAR_REGEX = re.compile(r"\b\d{4}\b")

    def resolve(
        self,
        current_question: str,
        state: Optional[ConversationState],
        followup: FollowupDetectionResult,
        *,
        prior_question: Optional[str] = None,
    ) -> ContinuationResolution:
        """Resolve query continuation semantically."""
        base_state = (state.active_query_state if state and state.active_query_state else SemanticQueryState())
        base_question = prior_question or ""

        if not followup.is_followup or followup.operation_type is None:
            return ContinuationResolution(
                is_resolved=False,
                resolved_question=current_question,
                updated_semantic_state=base_state,
                reason="Not a confirmed follow-up.",
            )

        op = followup.operation_type
        target = followup.target_value or ""

        # 1. LIMIT_CHANGE
        if op == FollowupType.LIMIT_CHANGE:
            try:
                new_limit = int(target)
            except ValueError:
                new_limit = 5

            updated_state = base_state.clone_with(limit=new_limit)

            # Rewrite question preserving original query
            if base_question and self._TOP_N_REGEX.search(base_question):
                resolved_q = self._TOP_N_REGEX.sub(f"top {new_limit}", base_question)
            elif base_question:
                resolved_q = f"Show top {new_limit} {base_question}"
            else:
                resolved_q = f"Top {new_limit}"

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=resolved_q,
                updated_semantic_state=updated_state,
                operation_applied=op,
            )

        # 2. TIME_CHANGE
        if op == FollowupType.TIME_CHANGE:
            filters = dict(base_state.filters)
            filters["time"] = target
            updated_state = base_state.clone_with(filters=filters, time_range=target)

            if base_question and self._MONTHS_YEARS_REGEX.search(base_question):
                # A year correction must replace the year token only.  The
                # previous broad pattern also matched the month in "January
                # 1, 2026", producing malformed text such as "2025 1, 2025".
                resolved_q = (
                    self._YEAR_REGEX.sub(target, base_question)
                    if self._YEAR_REGEX.fullmatch(target)
                    else self._MONTHS_YEARS_REGEX.sub(target, base_question)
                )
            elif base_question:
                resolved_q = f"{base_question} for {target}"
            else:
                resolved_q = f"Show data for {target}"

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=resolved_q,
                updated_semantic_state=updated_state,
                operation_applied=op,
            )

        # 3. GROUP_BY_CHANGE
        if op == FollowupType.GROUP_BY_CHANGE:
            new_group_by = (target,) if target else base_state.group_by
            updated_state = base_state.clone_with(group_by=new_group_by)

            clean_base = re.sub(r"\s+group\s+by\s+.*$", "", base_question, flags=re.IGNORECASE).strip()
            clean_base = re.sub(r"\s+by\s+.*$", "", clean_base, flags=re.IGNORECASE).strip()
            resolved_q = f"{clean_base} group by {target}" if clean_base else f"Group by {target}"

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=resolved_q,
                updated_semantic_state=updated_state,
                operation_applied=op,
            )

        # 4. SORT_CHANGE
        if op == FollowupType.SORT_CHANGE:
            new_order_by = (target,)
            updated_state = base_state.clone_with(order_by=new_order_by)
            resolved_q = f"{base_question}, {target}" if base_question else target

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=resolved_q,
                updated_semantic_state=updated_state,
                operation_applied=op,
            )

        # 5. FILTER_CHANGE / FILTER_ADDITION
        if op in (FollowupType.FILTER_CHANGE, FollowupType.FILTER_ADDITION):
            filters = dict(base_state.filters)
            filters["filter"] = target
            updated_state = base_state.clone_with(filters=filters)

            if "only" in current_question.lower() or "keep the same" in current_question.lower():
                # E.g. "Keep the same filters but only Egypt" -> "Show total sales for Egypt"
                # If base question exists:
                if base_question:
                    resolved_q = f"{base_question}, only {target}"
                else:
                    resolved_q = f"Only {target}"
            else:
                resolved_q = f"{base_question} for {target}" if base_question else target

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=resolved_q,
                updated_semantic_state=updated_state,
                operation_applied=op,
            )

        # 6. CORRECTION
        if op == FollowupType.CORRECTION:
            # Replaces the last conflicting token with target
            filters = dict(base_state.filters)
            filters["correction"] = target
            updated_state = base_state.clone_with(filters=filters)

            if base_question and self._MONTHS_YEARS_REGEX.search(base_question) and self._MONTHS_YEARS_REGEX.search(target):
                resolved_q = (
                    self._YEAR_REGEX.sub(target, base_question)
                    if self._YEAR_REGEX.fullmatch(target)
                    else self._MONTHS_YEARS_REGEX.sub(target, base_question)
                )
            elif base_question:
                resolved_q = f"{base_question} (corrected to {target})"
            else:
                resolved_q = target

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=resolved_q,
                updated_semantic_state=updated_state,
                operation_applied=op,
            )

        # 7. SAME_QUERY_DIFFERENT_SCOPE
        if op == FollowupType.SAME_QUERY_DIFFERENT_SCOPE:
            filters = dict(base_state.filters)
            filters["scope"] = target
            updated_state = base_state.clone_with(filters=filters)
            resolved_q = f"{base_question} for {target}" if base_question else target

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=resolved_q,
                updated_semantic_state=updated_state,
                operation_applied=op,
            )

        return ContinuationResolution(
            is_resolved=False,
            resolved_question=current_question,
            updated_semantic_state=base_state,
            reason=f"Unsupported continuation operation: {op}",
        )
