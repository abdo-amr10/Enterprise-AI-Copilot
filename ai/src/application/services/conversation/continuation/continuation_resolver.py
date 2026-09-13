"""Continuation Resolver that updates structured semantic query state without SQL string mutation."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.application.services.conversation.context_resolver import ContextResolver

from src.application.services.conversation.continuation.legacy_continuation_fallback import (
    LegacyContinuationFallbackResolver,
)
from src.application.services.conversation.extraction.entity_recognizer import (
    EntityRecognizer,
    get_entity_recognizer,
)
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

    _TOP_N_REGEX = re.compile(r"\b(?:top|first|limit)\s+(\d+|[a-zA-Z]+)\b", re.IGNORECASE)
    _YEAR_REGEX = re.compile(r"\b\d{4}\b")

    def __init__(
        self,
        *,
        context_resolver: Optional[Any] = None,
        entity_recognizer: Optional[EntityRecognizer] = None,
        enable_legacy_fallback: bool = True,
    ) -> None:
        self._context_resolver = context_resolver
        self._entity_recognizer = entity_recognizer or get_entity_recognizer()
        self._enable_legacy_fallback = enable_legacy_fallback
        self._legacy_fallback: Optional[LegacyContinuationFallbackResolver] = (
            LegacyContinuationFallbackResolver(entity_recognizer=self._entity_recognizer)
            if enable_legacy_fallback
            else None
        )

    @staticmethod
    def _replace_syntactic_slot(base_question: str, target: str) -> tuple[bool, str]:
        """Dynamically replace a prepositional argument slot in base_question with target."""
        clean_target = target.strip()
        formatted_target = clean_target.title() if (clean_target.islower() and " " not in clean_target) else clean_target

        prep_pattern = re.compile(
            r"\b(in|for|from|at)\s+((?:(?!\b(?:in|for|from|at|by|with)\b)[A-Za-z0-9_\-])+(?:\s+(?:(?!\b(?:in|for|from|at|by|with)\b)[A-Za-z0-9_\-]+)){0,2})(?:\s*[\.\?]?\s*)$",
            re.IGNORECASE,
        )
        match = prep_pattern.search(base_question)
        if not match:
            all_preps = re.compile(
                r"\b(in|for|from|at)\s+((?:(?!\b(?:in|for|from|at|by|with)\b)[A-Za-z0-9_\-])+(?:\s+(?:(?!\b(?:in|for|from|at|by|with)\b)[A-Za-z0-9_\-]+)){0,2})\b",
                re.IGNORECASE,
            )
            matches = list(all_preps.finditer(base_question))
            if matches:
                match = matches[-1]

        if match:
            if re.match(r"^(?:in|for|from|at)\s+", clean_target, re.IGNORECASE):
                resolved_q = base_question[:match.start()] + clean_target + base_question[match.end():]
            else:
                resolved_q = base_question[:match.start(2)] + formatted_target + base_question[match.end(2):]
            return True, resolved_q

        return False, base_question

    @staticmethod
    def _extract_base_entity_scope(base_question: str) -> str:
        """Dynamically extract the established entity scope / subject from a base query using specialist entity recognition."""
        if not base_question:
            return ""

        cleaned = re.sub(
            r"^(?:now\s+)?(?:finally,?\s+)?(?:please\s+)?(?:show|list|get|find|extract|pull|fetch|display|give\s+me|select)\s+(?:only\s+)?",
            "",
            base_question.strip(),
            flags=re.IGNORECASE,
        ).strip()

        cleaned = re.sub(r"[\.\?\!]+$", "", cleaned).strip()
        if not cleaned:
            return base_question.strip()

        for_match = re.search(r"\bfor\s+(?:the\s+)?([a-zA-Z0-9_\s]+?)(?:\s+using\s+.+)?$", cleaned, re.IGNORECASE)
        if for_match:
            entity_part = for_match.group(1).strip()
            if not re.match(r"^\d{4}$", entity_part):
                # Dynamically check whether entity_part is temporal using EntityRecognizer
                dt = get_entity_recognizer().extract_datetime(entity_part)
                if not dt:
                    return f"the {entity_part}" if not entity_part.lower().startswith("the ") else entity_part

        from_match = re.search(r"^from\s+(?:the\s+)?(.+?),\s*show", cleaned, re.IGNORECASE)
        if from_match:
            entity_part = from_match.group(1).strip()
            return f"the {entity_part}" if not entity_part.lower().startswith("the ") else entity_part

        if re.match(r"^(?:top|first|\d+)\b", cleaned, re.IGNORECASE):
            return f"the {cleaned}"
        return cleaned

    def resolve(
        self,
        current_question: str,
        state: Optional[ConversationState],
        followup: FollowupDetectionResult,
        *,
        prior_question: Optional[str] = None,
        prior_sql: Optional[str] = None,
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
                clean_base = re.sub(r"^(?:show|list|get|find|extract|pull|fetch)\s+", "", base_question, flags=re.IGNORECASE).strip()
                clean_base = re.sub(r"^all\s+", "", clean_base, flags=re.IGNORECASE).strip()
                resolved_q = f"Show top {new_limit} {clean_base}"
            else:
                resolved_q = f"Top {new_limit}"

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=resolved_q,
                updated_semantic_state=updated_state,
                operation_applied=op,
            )

        # 2. TIME_CHANGE (Dynamic date replacement via EntityRecognizer)
        if op == FollowupType.TIME_CHANGE:
            filters = dict(base_state.filters)
            filters["time"] = target
            updated_state = base_state.clone_with(filters=filters, time_range=target)

            if base_question and self._YEAR_REGEX.fullmatch(target) and self._YEAR_REGEX.search(base_question):
                resolved_q = self._YEAR_REGEX.sub(target, base_question)
            else:
                dt_results = self._entity_recognizer.extract_datetime(base_question) if base_question else []
                if dt_results:
                    dt = dt_results[0]
                    resolved_q = base_question[:dt.start_pos] + target + base_question[dt.end_pos:]
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

            # Primary Path: LLM-based ContextResolver if available
            if self._context_resolver and base_question:
                try:
                    retrieved_ctx: dict[str, Any] = {"prior_question": base_question}
                    if base_state.raw_sql:
                        retrieved_ctx["prior_sql"] = base_state.raw_sql
                    llm_resolved = self._context_resolver.resolve(current_question, retrieved_ctx)
                    if (
                        llm_resolved
                        and llm_resolved.strip()
                        and llm_resolved.strip().lower() != current_question.strip().lower()
                    ):
                        logger.info(
                            "ContextResolver (LLM) resolved follow-up: %r + %r -> %r",
                            base_question,
                            current_question,
                            llm_resolved,
                        )
                        filters["filter"] = target or current_question
                        return ContinuationResolution(
                            is_resolved=True,
                            resolved_question=llm_resolved.strip(),
                            updated_semantic_state=base_state.clone_with(filters=filters),
                            operation_applied=op,
                        )
                except Exception as exc:
                    logger.warning("ContextResolver LLM resolution failed, using fallback: %s", exc)

            # Quarantined Fallback Path for offline tests
            if self._legacy_fallback:
                resolved_q, updated_state = self._legacy_fallback.resolve_filter_fallback(
                    current_question=current_question,
                    base_question=base_question,
                    target=target,
                    base_state=base_state,
                )
                return ContinuationResolution(
                    is_resolved=True,
                    resolved_question=resolved_q,
                    updated_semantic_state=updated_state,
                    operation_applied=op,
                )

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=f"{base_question} for {target}" if base_question else target,
                updated_semantic_state=base_state.clone_with(filters=filters),
                operation_applied=op,
            )

        # 6. CORRECTION
        if op == FollowupType.CORRECTION:
            if self._legacy_fallback:
                resolved_q, updated_state = self._legacy_fallback.resolve_correction_fallback(
                    current_question=current_question,
                    base_question=base_question,
                    target=target,
                    base_state=base_state,
                )
                return ContinuationResolution(
                    is_resolved=True,
                    resolved_question=resolved_q,
                    updated_semantic_state=updated_state,
                    operation_applied=op,
                )

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=target,
                updated_semantic_state=base_state,
                operation_applied=op,
            )

        # 7. PRONOUN_REFERENCE
        if op == FollowupType.PRONOUN_REFERENCE:
            # Primary Path: LLM-based ContextResolver if available
            if self._context_resolver and base_question:
                try:
                    retrieved_ctx: dict[str, Any] = {"prior_question": base_question}
                    eff_sql = prior_sql or (base_state.raw_sql if base_state else None)
                    if eff_sql:
                        retrieved_ctx["prior_sql"] = eff_sql
                    scope_hint = self._extract_base_entity_scope(base_question)
                    if scope_hint:
                        retrieved_ctx["established_scope"] = scope_hint
                    llm_resolved = self._context_resolver.resolve(current_question, retrieved_ctx)
                    if (
                        llm_resolved
                        and llm_resolved.strip()
                        and llm_resolved.strip().lower() != current_question.strip().lower()
                    ):
                        logger.info(
                            "ContextResolver (LLM) resolved pronoun reference: %r + %r -> %r",
                            base_question,
                            current_question,
                            llm_resolved,
                        )
                        return ContinuationResolution(
                            is_resolved=True,
                            resolved_question=llm_resolved.strip(),
                            updated_semantic_state=base_state,
                            operation_applied=op,
                        )
                except Exception as exc:
                    logger.warning("ContextResolver LLM resolution failed, using fallback: %s", exc)

            # Quarantined Fallback Path for offline tests
            if self._legacy_fallback:
                resolved_q, updated_state = self._legacy_fallback.resolve_pronoun_reference_fallback(
                    current_question=current_question,
                    base_question=base_question,
                    base_state=base_state,
                )
                return ContinuationResolution(
                    is_resolved=True,
                    resolved_question=resolved_q,
                    updated_semantic_state=updated_state,
                    operation_applied=op,
                )

            return ContinuationResolution(
                is_resolved=True,
                resolved_question=current_question,
                updated_semantic_state=base_state,
                operation_applied=op,
            )

        return ContinuationResolution(
            is_resolved=False,
            resolved_question=current_question,
            updated_semantic_state=base_state,
            reason=f"Unsupported continuation operation: {op}",
        )
