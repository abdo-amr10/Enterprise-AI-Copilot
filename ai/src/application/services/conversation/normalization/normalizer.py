"""Deterministic request normalization for exact matching and fingerprinting."""

from __future__ import annotations

import re
import unicodedata


class RequestNormalizer:
    """Normalizes questions deterministically for exact matching and caching.

    Preserves semantic distinctions:
    - Numbers (e.g. "Top 5" vs "Top 10")
    - Dates (e.g. "January 2025" vs "January 2026")
    - Dimension tokens (e.g. "sales" vs "sales by region")
    """

    # Arabic tatweel and diacritics/tashkeel regex
    _ARABIC_TASHKEEL = re.compile(r"[\u064B-\u065F\u0670]")
    _ARABIC_TATWEEL = re.compile(r"\u0640")

    # Arabic alef variants to bare alef
    _ARABIC_ALEF = re.compile(r"[\u0622\u0623\u0625\u0671]")
    # Arabic alef maksura to yeh
    _ARABIC_ALEF_MAKSURA = re.compile(r"\u0649")
    # Arabic teh marbuta to heh
    _ARABIC_TEH_MARBUTA = re.compile(r"\u0629")

    # Safe punctuation stripping at edges or surrounding tokens
    _TRAILING_PUNCTUATION = re.compile(r"[?.!؟،,;:\'\"`~]+$")
    _LEADING_PUNCTUATION = re.compile(r"^[?.!؟،,;:\'\"`~]+")
    _MULTI_WHITESPACE = re.compile(r"\s+")

    @classmethod
    def normalize(cls, text: str) -> str:
        """Deterministically normalize the query text while preserving meaning."""
        if not text:
            return ""

        # 1. Unicode NFKC normalization
        normalized = unicodedata.normalize("NFKC", text)

        # 2. Case normalization (English / Latin)
        normalized = normalized.casefold()

        # 3. Arabic text normalization
        normalized = cls._ARABIC_TATWEEL.sub("", normalized)
        normalized = cls._ARABIC_TASHKEEL.sub("", normalized)
        normalized = cls._ARABIC_ALEF.sub("\u0627", normalized)
        normalized = cls._ARABIC_ALEF_MAKSURA.sub("\u064A", normalized)
        normalized = cls._ARABIC_TEH_MARBUTA.sub("\u0647", normalized)

        # 4. Collapse whitespace
        normalized = cls._MULTI_WHITESPACE.sub(" ", normalized).strip()

        # 5. Safe edge punctuation removal (e.g., question marks, quotes, trailing dots)
        normalized = cls._LEADING_PUNCTUATION.sub("", normalized)
        normalized = cls._TRAILING_PUNCTUATION.sub("", normalized).strip()

        # Final collapse in case punctuation trimming revealed extra spaces
        normalized = cls._MULTI_WHITESPACE.sub(" ", normalized).strip()
        return normalized
