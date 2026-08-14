import pytest

from ai.src.application.dto.llm.generation_request import GenerationRequest
from ai.src.application.dto.llm.generation_response import GenerationResponse


class TestGenerationRequest:
      
    """Tests for the GenerationRequest DTO."""

    def test_should_create_request_with_valid_prompt(self) -> None:
         """A valid prompt should create a GenerationRequest successfully."""

         request = GenerationRequest(prompt="Generate SQL for all customers.")

         assert request.prompt == "Generate SQL for all customers."

    def test_should_reject_empty_prompt(self) -> None:
        """An empty prompt should raise a ValueError.""" 

        with pytest.raises(ValueError,match="prompt cannot be empty"):
            GenerationRequest(prompt="")

    def test_should_reject_whitespace_only_prompt(self) -> None:
        """A whitespace-only prompt should raise a ValueError."""

        with pytest.raises(ValueError, match="prompt cannot be empty"):
            GenerationRequest(prompt="   ")         
  

class TestGenerationResponse:
    """Tests for the GenerationResponse DTO."""

    def test_should_create_response_with_valid_text(self) -> None:
        """Valid generated text should create a GenerationResponse successfully."""

        response = GenerationResponse(text="SELECT * FROM users")

        assert response.text == "SELECT * FROM users"

    
    def test_should_reject_empty_text(self) -> None:
        """Empty generated text should raise a ValueError."""

        with pytest.raises(ValueError,match="Generated text cannot be empty",):
            GenerationResponse(text="")


    def test_should_reject_whitespace_only_text(self) -> None:
        """Whitespace-only generated text should raise a ValueError."""       

        with pytest.raises(ValueError,match="Generated text cannot be empty",):
            GenerationResponse(text="  ")