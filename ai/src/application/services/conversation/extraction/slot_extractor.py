"""
Slot Extractor for Conversation Layer.

Extracts structured slot values (e.g. limit quantities, filter values, sort criteria,
group by attributes, corrections, and reset clean questions) from user utterances
in a deterministic, domain-agnostic manner.
"""
from __future__ import annotations

import re
from typing import Optional

from src.application.services.conversation.extraction.entity_recognizer import (
    EntityRecognizer,
    get_entity_recognizer,
)
from src.application.services.conversation.semantic_routing.domain.intent import ConversationIntent


class SlotExtractor:
    """Domain-agnostic extractor for conversation slot parameters."""

    # Retained as empty dict for backwards compatibility
    _WORD_TO_NUM: dict[str, str] = {}

    _RESET_PATTERN = re.compile(
        r"^(?:new\s+question[:\s]+|forget\s+(?:the\s+)?previous(?:\s+query|\s+question)?[\s.,;:]*|"
        r"start\s+over(?:\s+and)?[\s.,;:]*|reset(?:\s+context)?[\s.,;:]*|"
        r"start\s+fresh(?:\s+with\s+a\s+new\s+question)?[\s.,;:]*)(.+)$",
        re.IGNORECASE,
    )

    _GROUP_BY_PATTERN = re.compile(
        r"\b(?:by|according\s+to|into)\s+([a-zA-Z0-9_\s]+)$",
        re.IGNORECASE,
    )

    _SORT_BY_PATTERN = re.compile(
        r"\b(?:by|order\s+by|sort\s+by|rank\s+by)\s+(.+)$",
        re.IGNORECASE,
    )

    _FILTER_STRIP_PREFIX = re.compile(
        r"^(?:filter\s+by|what\s+about\s+(?:in|for)?|show\s+(?:the\s+)?(?:same|identical)\s+(?:report|data|thing)?\s+(?:for|in)?|and\s+(?:in|for)?|only|just|in|for)\s+",
        re.IGNORECASE,
    )

    @classmethod
    def word_to_number(cls, word: str) -> Optional[str]:
        """Convert a word representing a number to its digit string using specialist entity recognition."""
        if not word or not word.strip():
            return None
        nums = get_entity_recognizer().extract_numbers(word.strip())
        if nums:
            val = nums[0].value
            return str(int(val)) if val.is_integer() else str(val)
        return None

    @classmethod
    def extract_clean_question_after_reset(cls, text: str) -> Optional[str]:
        """Extract user question following a context reset expression."""
        m = cls._RESET_PATTERN.search(text)
        if m:
            clean = m.group(1).strip()
            if clean and clean.strip("?.,;:! "):
                return clean
            return None
        parts = re.split(r"[.;:\n]+", text, maxsplit=1)
        if len(parts) > 1:
            clean = parts[1].strip()
            if clean and clean.strip("?.,;:! "):
                return clean
        return None

    @classmethod
    def extract_limit(cls, text: str) -> str:
        """Extract limit number or return default '5' using specialist entity recognition."""
        return str(get_entity_recognizer().extract_limit(text, default=5))

    @classmethod
    def extract_group_by(cls, text: str) -> str:
        """Extract group-by attribute."""
        m = cls._GROUP_BY_PATTERN.search(text)
        if m:
            return m.group(1).strip()
        clean = re.sub(
            r"^(?:separate(?:\s+them)?|break\s+down(?:\s+them)?|group(?:\s+them)?)\s+",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        return clean or text

    @classmethod
    def extract_sort(cls, text: str) -> str:
        """Extract sort clause."""
        m = cls._SORT_BY_PATTERN.search(text)
        if m:
            return m.group(1).strip()
        clean = re.sub(
            r"^(?:please\s+)?(?:arrange|sort|order)\s+(?:them|the\s+output|the\s+results)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        return clean or text

    @classmethod
    def extract_filter(cls, text: str) -> str:
        """Extract filter target."""
        clean = cls._FILTER_STRIP_PREFIX.sub("", text).strip()
        clean = re.sub(r"^(?:in|for|at|from|with|to)\s+(?:the\s+)?", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"\s+only$", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"^[?.,\s]+|[?.,\s]+$", "", clean)
        return clean or text

    @classmethod
    def extract_correction(cls, text: str) -> str:
        """Extract correction value."""
        clean = text.strip()
        clean = re.sub(r"^(?:no|actually|correction)[:,\s]+", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(
            r"^(?:i\s+meant\s+|change\s+that\s+to\s+|make\s+that\s+|make\s+it\s+)",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()
        clean = re.sub(r"\s+instead$", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"^[?.,\s]+|[?.,\s]+$", "", clean)
        return clean or text

    @classmethod
    def extract_slot(cls, intent: ConversationIntent, text: str) -> str:
        """Extract slot value for a given conversation intent."""
        if intent == ConversationIntent.LIMIT_CHANGE:
            return cls.extract_limit(text)
        if intent == ConversationIntent.GROUP_BY_CHANGE:
            return cls.extract_group_by(text)
        if intent == ConversationIntent.SORT_CHANGE:
            return cls.extract_sort(text)
        if intent == ConversationIntent.FILTER_CHANGE:
            return cls.extract_filter(text)
        if intent == ConversationIntent.CORRECTION:
            return cls.extract_correction(text)
        return text
