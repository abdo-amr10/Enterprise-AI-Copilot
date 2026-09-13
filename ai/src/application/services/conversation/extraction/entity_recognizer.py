"""Entity Recognizer Service.

Specialist entity extraction abstraction utilizing Microsoft Recognizers-Text
for deterministic normalization of numbers, ordinals, dates, and durations.
Decoupled from application callers so underlying recognizer implementations can be replaced.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional, Union

from recognizers_text import Culture
from recognizers_number import recognize_number, recognize_ordinal
from recognizers_date_time import recognize_datetime

from src.application.services.conversation.models.semantic_intent_contract import TimeSpec


@dataclass(frozen=True)
class RecognizedNumber:
    text: str
    value: Union[int, float]
    start: int
    end: int


@dataclass(frozen=True)
class RecognizedOrdinal:
    text: str
    value: int
    start: int
    end: int


@dataclass(frozen=True)
class RecognizedDateTime:
    text: str
    type_name: str
    timex: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    value: Optional[str] = None
    mod: Optional[str] = None
    start_pos: int = 0
    end_pos: int = 0


class EntityRecognizer:
    """Specialist entity extractor abstraction for numbers, ordinals, and temporal expressions."""

    _ARABIC_INDIC_PATTERN = re.compile(r"[٠-٩]+")

    def __init__(self, default_culture: str = Culture.English) -> None:
        self._default_culture = default_culture

    def extract_numbers(
        self,
        text: str,
        culture: Optional[str] = None,
    ) -> List[RecognizedNumber]:
        """Extract all numbers (digits, English word forms, or Arabic-Indic numerals)."""
        if not text:
            return []
        effective_culture = culture or self._default_culture
        recognized = []

        try:
            results = recognize_number(text, effective_culture)
            if not results and text.strip() and " " not in text.strip():
                scale_results = recognize_number(f"a {text.strip()}", effective_culture)
                if scale_results:
                    for r in scale_results:
                        val = r.resolution.get("value")
                        if val is not None:
                            try:
                                num_val: Union[int, float] = int(val) if str(val).isdigit() or (isinstance(val, (int, float)) and int(val) == val) else float(val)
                            except (ValueError, TypeError):
                                continue
                            recognized.append(
                                RecognizedNumber(
                                    text=text.strip(),
                                    value=num_val,
                                    start=0,
                                    end=len(text.strip()),
                                )
                            )
            for r in results:
                val = r.resolution.get("value")
                if val is not None:
                    try:
                        num_val: Union[int, float] = int(val) if str(val).isdigit() or (isinstance(val, (int, float)) and int(val) == val) else float(val)
                    except (ValueError, TypeError):
                        continue
                    recognized.append(
                        RecognizedNumber(
                            text=r.text,
                            value=num_val,
                            start=r.start,
                            end=r.end + 1,
                        )
                    )
        except Exception:
            pass

        # Fallback support for Arabic-Indic numerals (٠-٩)
        for m in self._ARABIC_INDIC_PATTERN.finditer(text):
            try:
                num_val = int(m.group(0))
                recognized.append(
                    RecognizedNumber(
                        text=m.group(0),
                        value=num_val,
                        start=m.start(),
                        end=m.end(),
                    )
                )
            except (ValueError, TypeError):
                continue

        return recognized

    def extract_ordinals(
        self,
        text: str,
        culture: Optional[str] = None,
    ) -> List[RecognizedOrdinal]:
        """Extract ordinal numbers (e.g. 'first', 'second', '5th')."""
        if not text:
            return []
        effective_culture = culture or self._default_culture
        recognized = []
        try:
            results = recognize_ordinal(text, effective_culture)
            for r in results:
                val = r.resolution.get("value")
                if val is not None:
                    try:
                        num_val = int(val)
                    except (ValueError, TypeError):
                        continue
                    recognized.append(
                        RecognizedOrdinal(
                            text=r.text,
                            value=num_val,
                            start=r.start,
                            end=r.end + 1,
                        )
                    )
        except Exception:
            pass
        return recognized

    def extract_datetime(
        self,
        text: str,
        culture: Optional[str] = None,
        reference_datetime: Optional[datetime] = None,
    ) -> List[RecognizedDateTime]:
        """Extract dates, date ranges, and relative temporal expressions."""
        if not text:
            return []
        effective_culture = culture or self._default_culture
        ref = reference_datetime or datetime.now()
        recognized = []
        try:
            results = recognize_datetime(text, effective_culture, reference=ref)
            for r in results:
                vals = r.resolution.get("values") if r.resolution else None
                if vals and isinstance(vals, list) and len(vals) > 0:
                    first_val = vals[0]
                    val_point = first_val.get("value") or first_val.get("start")
                    recognized.append(
                        RecognizedDateTime(
                            text=r.text,
                            type_name=r.type_name,
                            timex=first_val.get("timex"),
                            start_date=first_val.get("start"),
                            end_date=first_val.get("end"),
                            value=val_point,
                            mod=first_val.get("Mod"),
                            start_pos=r.start,
                            end_pos=r.end + 1,
                        )
                    )
        except Exception:
            pass
        return recognized

    def extract_limit(self, text: str, default: int = 5) -> int:
        """Extract limit count from user utterance (supports digits, word numbers, ordinals, and Arabic-Indic)."""
        numbers = self.extract_numbers(text)
        ordinals = self.extract_ordinals(text)

        if numbers:
            val = numbers[0].value
            return int(val) if val > 0 else default
        if ordinals:
            val = ordinals[0].value
            return int(val) if val > 0 else default

        return default

    def extract_first_datetime_range(
        self,
        text: str,
        reference_datetime: Optional[datetime] = None,
    ) -> Optional[TimeSpec]:
        """Extract the first temporal constraint as a structured TimeSpec."""
        results = self.extract_datetime(text, reference_datetime=reference_datetime)
        if not results:
            return None
        dt = results[0]
        t_type = "date_range" if ("range" in dt.type_name.lower() or dt.end_date or dt.mod) else "date"
        return TimeSpec(
            source_text=dt.text,
            type=t_type,
            start=dt.start_date or dt.value,
            end=dt.end_date,
            timex=dt.timex,
        )


_default_entity_recognizer: Optional[EntityRecognizer] = None


def get_entity_recognizer() -> EntityRecognizer:
    """Get or create singleton instance of EntityRecognizer."""
    global _default_entity_recognizer
    if _default_entity_recognizer is None:
        _default_entity_recognizer = EntityRecognizer()
    return _default_entity_recognizer

