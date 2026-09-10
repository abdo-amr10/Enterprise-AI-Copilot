"""Unit tests for SlotExtractor in conversation layer."""

import pytest
from src.application.services.conversation.extraction.slot_extractor import SlotExtractor
from src.application.services.conversation.semantic_routing.domain.intent import ConversationIntent


class TestSlotExtractor:
    def test_word_to_number(self):
        assert SlotExtractor.word_to_number("one") == "1"
        assert SlotExtractor.word_to_number("five") == "5"
        assert SlotExtractor.word_to_number("twenty") == "20"
        assert SlotExtractor.word_to_number("hundred") == "100"
        assert SlotExtractor.word_to_number("unknown") is None

    def test_extract_limit_digits(self):
        assert SlotExtractor.extract_limit("Show top 10") == "10"
        assert SlotExtractor.extract_limit("first 25 rows") == "25"
        assert SlotExtractor.extract_limit("limit to 3") == "3"

    def test_extract_limit_words(self):
        assert SlotExtractor.extract_limit("Top five.") == "5"
        assert SlotExtractor.extract_limit("I only need the first seven.") == "7"
        assert SlotExtractor.extract_limit("Cap the output to twelve rows") == "12"

    def test_extract_limit_default(self):
        assert SlotExtractor.extract_limit("Just show results") == "5"

    def test_extract_group_by(self):
        assert SlotExtractor.extract_group_by("Separate them by branch") == "branch"
        assert SlotExtractor.extract_group_by("Group according to customer type") == "customer type"
        assert SlotExtractor.extract_group_by("Break down into regions") == "regions"
        assert SlotExtractor.extract_group_by("Group by department") == "department"

    def test_extract_sort(self):
        assert SlotExtractor.extract_sort("Arrange them by profit ascending") == "profit ascending"
        assert SlotExtractor.extract_sort("Order by balance from highest to lowest") == "balance from highest to lowest"
        assert SlotExtractor.extract_sort("Rank by score desc") == "score desc"

    def test_extract_filter(self):
        assert SlotExtractor.extract_filter("Filter by active customers only") == "active customers"
        assert SlotExtractor.extract_filter("What about in Miami?") == "Miami"
        assert SlotExtractor.extract_filter("Show the identical report for New York") == "New York"
        assert SlotExtractor.extract_filter("Only California") == "California"

    def test_extract_correction(self):
        assert SlotExtractor.extract_correction("Actually, make that below 500") == "below 500"
        assert SlotExtractor.extract_correction("No, change that to 2024 instead") == "2024"
        assert SlotExtractor.extract_correction("Correction: active users") == "active users"

    def test_extract_clean_question_after_reset(self):
        q1 = SlotExtractor.extract_clean_question_after_reset("New question: show all merchants.")
        assert q1 == "show all merchants."

        q2 = SlotExtractor.extract_clean_question_after_reset("Forget the previous query. Show all branches.")
        assert q2 == "Show all branches."

        q3 = SlotExtractor.extract_clean_question_after_reset("Start over and list all active accounts.")
        assert q3 == "list all active accounts."

        q4 = SlotExtractor.extract_clean_question_after_reset("Reset context.")
        assert q4 is None

    def test_extract_slot_dispatch(self):
        assert SlotExtractor.extract_slot(ConversationIntent.LIMIT_CHANGE, "Top ten") == "10"
        assert SlotExtractor.extract_slot(ConversationIntent.GROUP_BY_CHANGE, "by branch") == "branch"
        assert SlotExtractor.extract_slot(ConversationIntent.SORT_CHANGE, "by balance") == "balance"
        assert SlotExtractor.extract_slot(ConversationIntent.FILTER_CHANGE, "in Chicago") == "Chicago"
        assert SlotExtractor.extract_slot(ConversationIntent.CORRECTION, "Actually, 2023") == "2023"
        assert SlotExtractor.extract_slot(ConversationIntent.CAPABILITY, "What can you do?") == "What can you do?"
