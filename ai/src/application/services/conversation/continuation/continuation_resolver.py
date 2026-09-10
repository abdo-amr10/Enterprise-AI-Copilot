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
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december|\d{4}|last\s+year|last\s+month|this\s+year|this\s+month|q[1-4])\b",
        re.IGNORECASE,
    )

    _TOP_N_REGEX = re.compile(r"\b(?:top|first|limit)\s+(\d+)\b", re.IGNORECASE)
    _YEAR_REGEX = re.compile(r"\b\d{4}\b")

    @staticmethod
    def _replace_syntactic_slot(base_question: str, target: str) -> tuple[bool, str]:
        """Dynamically replace a prepositional argument slot in base_question with target.

        Agnostic to schema and entity types: works for locations (in New York -> in Chicago),
        departments (in HR -> in Marketing), products (for laptops -> for smartphones),
        statuses, categories, etc.
        """
        clean_target = target.strip()
        formatted_target = clean_target.title() if (clean_target.islower() and " " not in clean_target) else clean_target

        prep_pattern = re.compile(
            r"\b(in|for|from|at|by|with)\s+([A-Za-z0-9_\-]+(?:\s+[A-Za-z0-9_\-]+){0,3})\b",
            re.IGNORECASE,
        )
        matches = list(prep_pattern.finditer(base_question))
        if matches:
            last_match = matches[-1]
            if re.match(r"^(?:in|for|from|at|by|with)\s+", clean_target, re.IGNORECASE):
                resolved_q = base_question[:last_match.start()] + clean_target + base_question[last_match.end():]
            else:
                resolved_q = base_question[:last_match.start(2)] + formatted_target + base_question[last_match.end(2):]
            return True, resolved_q

        return False, base_question

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

            if base_question and self._TOP_N_REGEX.search(base_question):
                resolved_q = self._TOP_N_REGEX.sub(f"top {new_limit}", base_question)
            elif base_question:
                clean_base = re.sub(r"^(?:show|list|get|find)\s+", "", base_question, flags=re.IGNORECASE).strip()
                resolved_q = f"Show top {new_limit} {clean_base}"
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
            if clean_base:
                resolved_q = f"{clean_base} group by {target}"
            else:
                resolved_q = f"Group by {target}"

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
            clean_sort = re.sub(
                r"^(?:sort|order)(?:\s+(?:it|them|that|these|those))?\s*(?:by\s+)?",
                "",
                target,
                flags=re.IGNORECASE,
            ).strip()
            if clean_sort:
                resolved_q = f"{base_question}, sort by {clean_sort}" if base_question else f"Sort by {clean_sort}"
            else:
                resolved_q = f"{base_question}, {target}" if base_question else target

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=resolved_q,
                updated_semantic_state=updated_state,
                operation_applied=op,
            )

        # 5. FILTER_CHANGE / FILTER_ADDITION / SAME_QUERY_DIFFERENT_SCOPE
        if op in (FollowupType.FILTER_CHANGE, FollowupType.FILTER_ADDITION, FollowupType.SAME_QUERY_DIFFERENT_SCOPE):
            filters = dict(base_state.filters)

            replaced = False
            for k, v in list(filters.items()):
                if v and isinstance(v, str) and re.search(r"\b" + re.escape(v) + r"\b", base_question, re.IGNORECASE):
                    resolved_q = re.sub(r"\b" + re.escape(v) + r"\b", target.title() if target.islower() else target, base_question, flags=re.IGNORECASE)
                    filters[k] = target
                    replaced = True
                    break

            if not replaced:
                slot_replaced, resolved_q = self._replace_syntactic_slot(base_question, target)
                if slot_replaced:
                    filters["filter"] = target
                    replaced = True

            if not replaced:
                if "only" in current_question.lower() or "keep the same" in current_question.lower():
                    resolved_q = f"{base_question}, only {target}" if base_question else f"Only {target}"
                else:
                    resolved_q = f"{base_question} for {target}" if base_question else target
                filters["filter"] = target

            updated_state = base_state.clone_with(filters=filters)
            return ContinuationResolution(
                is_resolved=True,
                resolved_question=resolved_q,
                updated_semantic_state=updated_state,
                operation_applied=op,
            )

        # 6. CORRECTION
        if op == FollowupType.CORRECTION:
            filters = dict(base_state.filters)

            # "Not X — show Y instead" / "Instead of X, show Y"
            m_not = re.search(r"(?:not|instead\s+of)\s+([a-zA-Z0-9_]+).*?(?:show\s+)?([a-zA-Z0-9_]+)\s+instead", current_question, re.IGNORECASE)
            if not m_not:
                m_not = re.search(r"not\s+([a-zA-Z0-9_]+).*?(?:show|use)\s+([a-zA-Z0-9_]+)", current_question, re.IGNORECASE)
            if m_not:
                old_val, new_val = m_not.group(1), m_not.group(2)
                resolved_q = re.sub(r"\b" + re.escape(old_val) + r"\b", new_val.title(), base_question, flags=re.IGNORECASE)
                filters["correction"] = new_val
                return ContinuationResolution(
                    is_resolved=True,
                    resolved_question=resolved_q,
                    updated_semantic_state=base_state.clone_with(filters=filters),
                    operation_applied=op,
                )

            # Full query rewrite: "Actually, show customers in Chicago instead"
            m_show = re.search(r"(?:show|list|get|find)\s+(.+?)(?:\s+instead)?$", target, re.IGNORECASE)
            if m_show:
                resolved_q = f"Show {m_show.group(1).strip()}"
                filters["correction"] = target
                return ContinuationResolution(
                    is_resolved=True,
                    resolved_question=resolved_q,
                    updated_semantic_state=base_state.clone_with(filters=filters),
                    operation_applied=op,
                )

            # Year correction: "Actually, make that 2026"
            m_year = re.search(r"\b(\d{4})\b", target)
            if m_year and re.search(r"\b\d{4}\b", base_question):
                new_yr = m_year.group(1)
                resolved_q = self._YEAR_REGEX.sub(new_yr, base_question)
                filters["time"] = new_yr
                return ContinuationResolution(
                    is_resolved=True,
                    resolved_question=resolved_q,
                    updated_semantic_state=base_state.clone_with(filters=filters, time_range=new_yr),
                    operation_applied=op,
                )

            # Numeric comparison correction: "Actually, below 600"
            num_cond_pattern = r"(?:below|above|less\s+than|greater\s+than|<|>|<=|>=)\s*(\d+)"
            m_num_cond = re.search(num_cond_pattern, target, re.IGNORECASE)
            if m_num_cond and re.search(num_cond_pattern, base_question, re.IGNORECASE):
                resolved_q = re.sub(num_cond_pattern, target, base_question, flags=re.IGNORECASE)
                filters["correction"] = target
                return ContinuationResolution(
                    is_resolved=True,
                    resolved_question=resolved_q,
                    updated_semantic_state=base_state.clone_with(filters=filters),
                    operation_applied=op,
                )

            # Prepositional slot correction: "No, Chicago" or "Actually, Miami"
            clean_target = re.sub(r"^(?:no[,]?\s*(?:i\s+meant\s+)?|actually[,]?\s*(?:make\s+that\s+)?|correction[:\s]+)", "", current_question, flags=re.IGNORECASE).strip()
            slot_replaced, resolved_q = self._replace_syntactic_slot(base_question, clean_target)
            if slot_replaced:
                filters["correction"] = clean_target
                return ContinuationResolution(
                    is_resolved=True,
                    resolved_question=resolved_q,
                    updated_semantic_state=base_state.clone_with(filters=filters),
                    operation_applied=op,
                )

            # Default date/generic correction
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

            filters["correction"] = target
            return ContinuationResolution(
                is_resolved=True,
                resolved_question=resolved_q,
                updated_semantic_state=base_state.clone_with(filters=filters),
                operation_applied=op,
            )

        # 7. PRONOUN_REFERENCE
        if op == FollowupType.PRONOUN_REFERENCE:
            clean_prior = re.sub(r"^(?:show|list|get|find)\s+", "", base_question, flags=re.IGNORECASE).rstrip(".?")
            clean_curr = re.sub(r"\b(?:of\s+them|among\s+them|from\s+them)\b", "", current_question, flags=re.IGNORECASE).strip(" ?.")
            if clean_prior and clean_curr:
                resolved_q = f"Among {clean_prior}, {clean_curr}"
            else:
                resolved_q = current_question

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=resolved_q,
                updated_semantic_state=base_state,
                operation_applied=op,
            )

        return ContinuationResolution(
            is_resolved=False,
            resolved_question=current_question,
            updated_semantic_state=base_state,
            reason=f"Unsupported continuation operation: {op}",
        )
