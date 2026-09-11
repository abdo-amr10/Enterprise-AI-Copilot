"""
Slot Extractor for Conversation Layer.

Extracts structured slot values (e.g. limit quantities, filter values, sort criteria,
group by attributes, corrections, and reset clean questions) from user utterances
in a deterministic, domain-agnostic manner.
"""
from __future__ import annotations

import re
from typing import Optional

from src.application.services.conversation.semantic_routing.domain.intent import ConversationIntent


class SlotExtractor:
    """Domain-agnostic extractor for conversation slot parameters."""

    _WORD_TO_NUM: dict[str, str] = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
        "eleven": "11",
        "twelve": "12",
        "fifteen": "15",
        "twenty": "20",
        "fifty": "50",
        "hundred": "100",
    }

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
        """Convert an English word representing a number to its digit string."""
        return cls._WORD_TO_NUM.get(word.lower().strip())

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
        """Extract limit number or return default '5'."""
        num_match = re.search(r"\b(\d+)\b", text)
        if num_match:
            return num_match.group(1)
        num_words_regex = r"\b(" + "|".join(cls._WORD_TO_NUM.keys()) + r")\b"
        m = re.search(num_words_regex, text, re.IGNORECASE)
        if m:
            return cls._WORD_TO_NUM.get(m.group(1).lower(), "5")
        return "5"

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
