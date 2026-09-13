"""
=============================================================================
DEPRECATED - TEST & OFFLINE FALLBACK ONLY
=============================================================================
This module contains legacy syntactic regexes and heuristic query rewriting
retained EXCLUSIVELY for backwards compatibility with legacy offline unit
tests that execute without an active ContextResolver (LLM).

IN PRODUCTION:
When ContextResolver is configured with the local LLM, continuation and
pronoun resolution are performed dynamically by the LLM without regexes.

TO DELETE IN THE FUTURE:
When legacy unit tests are retired or migrated to LLM-grounded fixtures,
this file can be safely deleted in its entirety.
=============================================================================
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from src.application.services.conversation.extraction.entity_recognizer import (
    EntityRecognizer,
    get_entity_recognizer,
)
from src.application.services.conversation.followup.models import (
    FollowupDetectionResult,
    FollowupType,
)
from src.application.services.conversation.state.conversation_state import (
    ConversationState,
    SemanticQueryState,
)

logger = logging.getLogger(__name__)


class LegacyContinuationFallbackResolver:
    """Legacy heuristic query rewriter used strictly as an offline test fallback."""

    _TOP_N_REGEX = re.compile(r"\b(?:top|first|limit)\s+(\d+|[a-zA-Z]+)\b", re.IGNORECASE)
    _YEAR_REGEX = re.compile(r"\b\d{4}\b")

    def __init__(self, entity_recognizer: Optional[EntityRecognizer] = None) -> None:
        self._entity_recognizer = entity_recognizer or get_entity_recognizer()

    def replace_syntactic_slot(self, base_question: str, target: str) -> tuple[bool, str]:
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

    def extract_base_entity_scope(self, base_question: str) -> str:
        """Extract the established entity scope / subject from a base query."""
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
                dt = self._entity_recognizer.extract_datetime(entity_part)
                if not dt:
                    return f"the {entity_part}" if not entity_part.lower().startswith("the ") else entity_part

        from_match = re.search(r"^from\s+(?:the\s+)?(.+?),\s*show", cleaned, re.IGNORECASE)
        if from_match:
            entity_part = from_match.group(1).strip()
            return f"the {entity_part}" if not entity_part.lower().startswith("the ") else entity_part

        if re.match(r"^(?:top|first|\d+)\b", cleaned, re.IGNORECASE):
            return f"the {cleaned}"
        return cleaned

    def resolve_pronoun_reference_fallback(
        self,
        current_question: str,
        base_question: str,
        base_state: SemanticQueryState,
    ) -> tuple[str, SemanticQueryState]:
        """Apply Pattern A through F heuristic rewrites for pronoun reference."""
        scope = self.extract_base_entity_scope(base_question)
        clean_curr = current_question.strip()

        # Pattern A: "Go back to ... from before and <action>"
        m_goback = re.search(
            r"^go\s+back\s+to\s+(?:the\s+)?(.+?)(?:\s+from\s+before)?\s+and\s+(.+)$",
            clean_curr,
            re.IGNORECASE,
        )
        if m_goback:
            action = m_goback.group(2).strip()
            if re.search(r"\btheir\b", action, re.IGNORECASE):
                action_cleaned = re.sub(r"\btheir\s+", "", action, flags=re.IGNORECASE).strip()
                resolved_q = f"{action_cleaned.capitalize()} for {scope}"
            else:
                resolved_q = f"{action.capitalize()} for {scope}"
            return resolved_q, base_state

        # Pattern B: "For those same <entities>, <action>"
        m_for_those = re.search(
            r"^for\s+(?:those\s+same|those|the\s+same|these\s+same|these|the)\s+([a-zA-Z0-9_]+)(?:\s+above|\s+from\s+before)?,\s*(.+)$",
            clean_curr,
            re.IGNORECASE,
        )
        if m_for_those:
            action = m_for_those.group(2).strip()
            if re.search(r"\btheir\b", action, re.IGNORECASE):
                action_cleaned = re.sub(r"\btheir\s+", "", action, flags=re.IGNORECASE).strip()
                resolved_q = f"{action_cleaned.capitalize()} for {scope}"
            else:
                resolved_q = f"{action.capitalize()} for {scope}"
            return resolved_q, base_state

        # Pattern C: "... for the same <entities>"
        m_for_same = re.search(
            r"\bfor\s+(?:the\s+same|those\s+same|those)\s+([a-zA-Z0-9_]+)\b",
            clean_curr,
            re.IGNORECASE,
        )
        if m_for_same:
            resolved_q = clean_curr[:m_for_same.start()] + f"for {scope}" + clean_curr[m_for_same.end():]
            return resolved_q.strip(), base_state

        # Pattern D: "... of those top N <entities>"
        m_of_those = re.search(
            r"\b(?:of|for\s+each\s+of)\s+those(?:\s+top\s+\d+)?\s+([a-zA-Z0-9_]+)\b",
            clean_curr,
            re.IGNORECASE,
        )
        if m_of_those:
            resolved_q = clean_curr[:m_of_those.start()] + f"for {scope}" + clean_curr[m_of_those.end():]
            return resolved_q.strip(), base_state

        # Pattern E: "Now show only <entities> whose <condition>"
        m_whose = re.search(
            r"^(?:now\s+)?show\s+only\s+([a-zA-Z0-9_]+)\s+whose\s+(.+)$",
            clean_curr,
            re.IGNORECASE,
        )
        if m_whose:
            condition = m_whose.group(2).strip()
            resolved_q = f"From {scope}, show only those whose {condition}"
            return resolved_q, base_state

        # Pattern F: "Which of them...", "Sort them...", "Filter them..."
        if re.search(r"\b(?:of\s+them|among\s+them|from\s+them|them)\b", clean_curr, re.IGNORECASE):
            clean_prior = scope or base_question
            clean_curr_sub = re.sub(r"\b(?:of\s+them|among\s+them|from\s+them)\b", "", clean_curr, flags=re.IGNORECASE).strip(" ?.")
            if clean_curr_sub != clean_curr.strip(" ?."):
                resolved_q = f"Among {clean_prior}, {clean_curr_sub}"
            else:
                resolved_q = re.sub(r"\bthem\b", clean_prior, clean_curr, flags=re.IGNORECASE)
            return resolved_q, base_state

        if scope:
            resolved_q = f"{clean_curr} (for {scope})"
        else:
            resolved_q = clean_curr

        return resolved_q, base_state

    def resolve_filter_fallback(
        self,
        current_question: str,
        base_question: str,
        target: str,
        base_state: SemanticQueryState,
    ) -> tuple[str, SemanticQueryState]:
        """Apply heuristic filter and scope replacements."""
        filters = dict(base_state.filters)

        m_whose = re.search(
            r"^(?:now\s+)?show\s+only\s+([a-zA-Z0-9_]+)\s+whose\s+(.+)$",
            current_question.strip(),
            re.IGNORECASE,
        )
        if m_whose:
            condition = m_whose.group(2).strip()
            scope = self.extract_base_entity_scope(base_question)
            resolved_q = f"From {scope}, show only those whose {condition}"
            filters["filter"] = condition
            return resolved_q, base_state.clone_with(filters=filters)

        replaced = False
        for k, v in list(filters.items()):
            if v and isinstance(v, str) and re.search(r"\b" + re.escape(v) + r"\b", base_question, re.IGNORECASE):
                resolved_q = re.sub(r"\b" + re.escape(v) + r"\b", target.title() if target.islower() else target, base_question, flags=re.IGNORECASE)
                filters[k] = target
                replaced = True
                break

        if not replaced:
            slot_replaced, resolved_q = self.replace_syntactic_slot(base_question, target)
            if slot_replaced:
                filters["filter"] = target
                replaced = True

        if not replaced:
            if "only" in current_question.lower() or "keep the same" in current_question.lower():
                resolved_q = f"{base_question}, only {target}" if base_question else f"Only {target}"
            else:
                resolved_q = f"{base_question} for {target}" if base_question else target
            filters["filter"] = target

        return resolved_q, base_state.clone_with(filters=filters)

    def resolve_correction_fallback(
        self,
        current_question: str,
        base_question: str,
        target: str,
        base_state: SemanticQueryState,
    ) -> tuple[str, SemanticQueryState]:
        """Apply heuristic correction rewrites."""
        filters = dict(base_state.filters)

        m_not = re.search(r"(?:not|instead\s+of)\s+([a-zA-Z0-9_]+).*?(?:show\s+)?([a-zA-Z0-9_]+)\s+instead", current_question, re.IGNORECASE)
        if not m_not:
            m_not = re.search(r"not\s+([a-zA-Z0-9_]+).*?(?:show|use)\s+([a-zA-Z0-9_]+)", current_question, re.IGNORECASE)
        if m_not:
            old_val, new_val = m_not.group(1), m_not.group(2)
            resolved_q = re.sub(r"\b" + re.escape(old_val) + r"\b", new_val.title(), base_question, flags=re.IGNORECASE)
            filters["correction"] = new_val
            return resolved_q, base_state.clone_with(filters=filters)

        m_show = re.search(r"(?:show|list|get|find)\s+(.+?)(?:\s+instead)?$", target, re.IGNORECASE)
        if m_show:
            resolved_q = f"Show {m_show.group(1).strip()}"
            filters["correction"] = target
            return resolved_q, base_state.clone_with(filters=filters)

        m_year = re.search(r"\b(\d{4})\b", target)
        if m_year and re.search(r"\b\d{4}\b", base_question):
            new_yr = m_year.group(1)
            resolved_q = self._YEAR_REGEX.sub(new_yr, base_question)
            filters["time"] = new_yr
            return resolved_q, base_state.clone_with(filters=filters, time_range=new_yr)

        num_cond_pattern = r"(?:below|above|less\s+than|greater\s+than|<|>|<=|>=)\s*(\d+)"
        m_num_cond = re.search(num_cond_pattern, target, re.IGNORECASE)
        if m_num_cond and re.search(num_cond_pattern, base_question, re.IGNORECASE):
            resolved_q = re.sub(num_cond_pattern, target, base_question, flags=re.IGNORECASE)
            filters["correction"] = target
            return resolved_q, base_state.clone_with(filters=filters)

        clean_target = re.sub(r"^(?:no[,]?\s*(?:i\s+meant\s+)?|actually[,]?\s*(?:make\s+that\s+)?|correction[:\s]+)", "", current_question, flags=re.IGNORECASE).strip()
        slot_replaced, resolved_q = self.replace_syntactic_slot(base_question, clean_target)
        if slot_replaced:
            filters["correction"] = clean_target
            return resolved_q, base_state.clone_with(filters=filters)

        # Dynamic datetime replacement via EntityRecognizer
        dt_base = self._entity_recognizer.extract_datetime(base_question) if base_question else []
        dt_target = self._entity_recognizer.extract_datetime(target) if target else []
        if dt_base and dt_target:
            dt = dt_base[0]
            resolved_q = base_question[:dt.start_pos] + target + base_question[dt.end_pos:]
        elif base_question:
            resolved_q = f"{base_question} (corrected to {target})"
        else:
            resolved_q = target

        filters["correction"] = target
        return resolved_q, base_state.clone_with(filters=filters)
