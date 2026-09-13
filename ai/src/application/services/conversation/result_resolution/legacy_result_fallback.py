"""
=============================================================================
DEPRECATED - TEST & OFFLINE FALLBACK ONLY
=============================================================================
This module contains legacy hardcoded ordinal maps and cross-script name
dictionaries retained EXCLUSIVELY for backwards compatibility with legacy
offline test fixtures.

IN PRODUCTION:
In the English-only enterprise copilot, ordinals are normalized dynamically
by `EntityRecognizer` (Microsoft Recognizers-Text).

TO DELETE IN THE FUTURE:
When legacy unit tests are retired or migrated to EntityRecognizer assertions,
this file can be safely deleted in its entirety.
=============================================================================
"""
from __future__ import annotations

import re
from typing import Optional


class LegacyResultFallback:
    """Quarantined legacy dictionaries for offline test backwards compatibility."""

    _ORDINAL_WORDS: dict[str, int] = {
        "first": 1,
        "1st": 1,
        "second": 2,
        "2nd": 2,
        "third": 3,
        "3rd": 3,
        "fourth": 4,
        "4th": 4,
        "fifth": 5,
        "5th": 5,
        "sixth": 6,
        "6th": 6,
        "seventh": 7,
        "7th": 7,
        "eighth": 8,
        "8th": 8,
        "ninth": 9,
        "9th": 9,
        "tenth": 10,
        "10th": 10,
        "eleventh": 11,
        "11th": 11,
        "twelfth": 12,
        "12th": 12,
        "thirteenth": 13,
        "13th": 13,
        "fourteenth": 14,
        "14th": 14,
        "fifteenth": 15,
        "15th": 15,
        "sixteenth": 16,
        "16th": 16,
        "seventeenth": 17,
        "17th": 17,
        "eighteenth": 18,
        "18th": 18,
        "nineteenth": 19,
        "19th": 19,
        "twentieth": 20,
        "20th": 20,
        "الأول": 1,
        "الاول": 1,
        "الثاني": 2,
        "التاني": 2,
        "الثالث": 3,
        "التالت": 3,
        "الرابع": 4,
        "الخامس": 5,
        "السادس": 6,
        "السابع": 7,
        "الثامن": 8,
        "التاسع": 9,
        "العاشر": 10,
    }

    _ARABIC_TO_LATIN_COMMON: dict[str, str] = {
        "سارة": "sara",
        "ساره": "sara",
        "احمد": "ahmed",
        "أحمد": "ahmed",
        "محمد": "mohamed",
        "علي": "ali",
        "خالد": "khaled",
        "تامر": "tamer",
        "محمود": "mahmoud",
        "عمرو": "amr",
        "منى": "mona",
        "مني": "mona",
        "طارق": "tarek",
        "حسن": "hassan",
        "حسين": "hussein",
        "ابراهيم": "ibrahim",
        "إبراهيم": "ibrahim",
        "مريم": "mariam",
        "فاطمة": "fatima",
        "نور": "nour",
    }

    @classmethod
    def lookup_ordinal(cls, word: Optional[str]) -> Optional[int]:
        """Look up ordinal rank from legacy dictionary."""
        if not word:
            return None
        return cls._ORDINAL_WORDS.get(word.strip().lower())

    @classmethod
    def match_transliteration(cls, cell_clean: str, norm_q: str) -> bool:
        """Check cross-script transliteration from legacy dictionary."""
        ar_variant = cls._ARABIC_TO_LATIN_COMMON.get(cell_clean)
        if ar_variant and re.search(r"\b" + re.escape(ar_variant) + r"\b", norm_q):
            return True
        for ar_w, en_w in cls._ARABIC_TO_LATIN_COMMON.items():
            if en_w == cell_clean and ar_w in norm_q:
                return True
        return False
