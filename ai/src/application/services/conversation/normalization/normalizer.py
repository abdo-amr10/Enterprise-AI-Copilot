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

    # Safe punctuation stripping at edges or surrounding tokens
    _TRAILING_PUNCTUATION = re.compile(r"[?.!,;:\'\"`~]+$")
    _LEADING_PUNCTUATION = re.compile(r"^[?.!,;:\'\"`~]+")
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

        # 3. Collapse whitespace
        normalized = cls._MULTI_WHITESPACE.sub(" ", normalized).strip()

        # 4. Safe edge punctuation removal (e.g., question marks, quotes, trailing dots)
        normalized = cls._LEADING_PUNCTUATION.sub("", normalized)
        normalized = cls._TRAILING_PUNCTUATION.sub("", normalized).strip()

        # Final collapse in case punctuation trimming revealed extra spaces
        normalized = cls._MULTI_WHITESPACE.sub(" ", normalized).strip()
        return normalized
