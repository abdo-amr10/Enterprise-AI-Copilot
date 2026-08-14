import pytest

from ai.src.application.dto.llm.generation_request import GenerationRequest
from src.application.services.text_to_sql.prompt_service import PromptService


class TestPromptService:
    """Tests for the Text-to-SQL PromptService."""

    def setup_method(self) -> None:
        """Create a PromptService instance before each test."""
        self.service = PromptService()

    def test_build_request_returns_generation_request(self) -> None:
        """Build request should return a GenerationRequest object."""
        question = "Show all customers."
        semantic_context = "Customer entity from the semantic layer."
        current_date = "2026-08-12"

        result = self.service.build_request(
            question=question,
            semantic_context=semantic_context,
            current_date=current_date,
        )

        assert isinstance(result, GenerationRequest)

    def test_build_request_includes_question(self) -> None:
        """The generated prompt should contain the user question."""
        question = "Show all customers."
        semantic_context = "Customer entity from the semantic layer."
        current_date = "2026-08-12"

        result = self.service.build_request(
            question=question,
            semantic_context=semantic_context,
            current_date=current_date,
        )

        assert question in result.prompt

    def test_build_request_includes_semantic_context(self) -> None:
        """The generated prompt should contain the semantic context."""
        question = "Show all customers."
        semantic_context = """
        Entity: Customer
        Table: customers
        Primary Key: customer_id
        """
        current_date = "2026-08-12"

        result = self.service.build_request(
            question=question,
            semantic_context=semantic_context,
            current_date=current_date,
        )

        assert semantic_context in result.prompt

    def test_build_request_includes_current_date(self) -> None:
        """The generated prompt should contain the reference date."""
        question = "Show customers from this month."
        semantic_context = "Customer entity from the semantic layer."
        current_date = "2026-08-12"

        result = self.service.build_request(
            question=question,
            semantic_context=semantic_context,
            current_date=current_date,
        )

        assert current_date in result.prompt

    def test_build_request_includes_text_to_sql_instructions(self) -> None:
        """The generated prompt should contain the required SQL instructions."""
        question = "Show all customers."
        semantic_context = "Customer entity from the semantic layer."
        current_date = "2026-08-12"

        result = self.service.build_request(
            question=question,
            semantic_context=semantic_context,
            current_date=current_date,
        )

        assert "Microsoft SQL Server" in result.prompt
        assert "read-only" in result.prompt
        assert "semantic context" in result.prompt

    def test_build_request_rejects_empty_semantic_context(self) -> None:
        """An empty semantic context should be rejected."""
        question = "Show all customers."
        current_date = "2026-08-12"

        with pytest.raises(
            ValueError,
            match="semantic_context cannot be empty",
        ):
            self.service.build_request(
                question=question,
                semantic_context="",
                current_date=current_date,
            )

    def test_build_request_rejects_whitespace_semantic_context(self) -> None:
        """Whitespace-only semantic context should be rejected."""
        question = "Show all customers."
        current_date = "2026-08-12"

        with pytest.raises(
            ValueError,
            match="semantic_context cannot be empty",
        ):
            self.service.build_request(
                question=question,
                semantic_context="   ",
                current_date=current_date,
            )