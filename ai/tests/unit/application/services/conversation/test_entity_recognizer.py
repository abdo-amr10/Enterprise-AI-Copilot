"""Unit tests for EntityRecognizer service abstraction."""
from datetime import datetime
import pytest

from src.application.services.conversation.extraction.entity_recognizer import (
    EntityRecognizer,
    RecognizedNumber,
    RecognizedOrdinal,
    RecognizedDateTime,
)


@pytest.fixture
def recognizer() -> EntityRecognizer:
    return EntityRecognizer()


def test_extract_numbers_digits(recognizer: EntityRecognizer):
    numbers = recognizer.extract_numbers("Show 25 customers with 100 accounts")
    assert len(numbers) == 2
    assert numbers[0].value == 25
    assert numbers[1].value == 100


def test_extract_numbers_words(recognizer: EntityRecognizer):
    numbers = recognizer.extract_numbers("Show me the top twenty five customers")
    assert len(numbers) == 1
    assert numbers[0].value == 25
    assert numbers[0].text == "twenty five"


def test_extract_numbers_compound_words(recognizer: EntityRecognizer):
    numbers = recognizer.extract_numbers("Limit to three hundred and fifty records")
    assert len(numbers) == 1
    assert numbers[0].value == 350


def test_extract_numbers_arabic_indic(recognizer: EntityRecognizer):
    numbers = recognizer.extract_numbers("أعلى ٥ عملاء")
    assert len(numbers) >= 1
    assert numbers[0].value == 5


def test_extract_ordinals(recognizer: EntityRecognizer):
    ordinals = recognizer.extract_ordinals("Give me the first and the fifth customer")
    assert len(ordinals) == 2
    assert ordinals[0].value == 1
    assert ordinals[0].text == "first"
    assert ordinals[1].value == 5
    assert ordinals[1].text == "fifth"


def test_extract_limit_helper(recognizer: EntityRecognizer):
    assert recognizer.extract_limit("top 10") == 10
    assert recognizer.extract_limit("first five") == 5
    assert recognizer.extract_limit("twenty five records") == 25
    assert recognizer.extract_limit("أعلى ٥", default=5) == 5
    assert recognizer.extract_limit("show all users", default=5) == 5


def test_extract_datetime_relative_and_ranges(recognizer: EntityRecognizer):
    ref_time = datetime(2026, 9, 12, 12, 0, 0)
    
    # Yesterday
    dts_yesterday = recognizer.extract_datetime("Show transactions from yesterday", reference_datetime=ref_time)
    assert len(dts_yesterday) >= 1
    assert dts_yesterday[0].value == "2026-09-11"

    # Last month
    dts_month = recognizer.extract_datetime("Show sales last month", reference_datetime=ref_time)
    assert len(dts_month) >= 1
    assert dts_month[0].start_date == "2026-08-01"
    assert dts_month[0].end_date == "2026-09-01"


def test_extract_first_datetime_range(recognizer: EntityRecognizer):
    ref_time = datetime(2026, 9, 12, 12, 0, 0)
    time_spec = recognizer.extract_first_datetime_range("orders last month", reference_datetime=ref_time)
    assert time_spec is not None
    assert time_spec.type == "date_range"
    assert time_spec.start == "2026-08-01"
    assert time_spec.end == "2026-09-01"


def test_empty_or_no_entities(recognizer: EntityRecognizer):
    assert recognizer.extract_numbers("") == []
    assert recognizer.extract_ordinals("") == []
    assert recognizer.extract_datetime("") == []
    assert recognizer.extract_numbers("just plain text without numbers") == []
