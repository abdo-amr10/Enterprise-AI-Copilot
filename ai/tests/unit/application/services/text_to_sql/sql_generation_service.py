"""Unit tests for the SQLGenerationService."""

from unittest.mock import Mock

import pytest

from ai.src.application.dto.llm.generation_request import GenerationRequest
from ai.src.application.dto.llm.generation_response import GenerationResponse
from src.application.services.text_to_sql.sql_generation_service import SQLGenerationService


def test_generate_delegates_to_llm_client():
    """Verify that the generation request is delegated to the LLM client."""

    request = GenerationRequest(
        prompt="Generate SQL for customers."
    )

    expected_response = GenerationResponse(
        text="SELECT * FROM customers;"
    )

    llm_client = Mock()
    llm_client.generate.return_value = expected_response

    service = SQLGenerationService(llm_client)

    result = service.generate(request)

    assert result == expected_response
    llm_client.generate.assert_called_once_with(request)


def test_generate_propagates_llm_error():
    """Verify that LLM client errors are propagated to the caller."""

    request = GenerationRequest(
        prompt="Generate SQL."
    )

    llm_client = Mock()
    llm_client.generate.side_effect = RuntimeError("LLM unavailable")

    service = SQLGenerationService(llm_client)

    with pytest.raises(RuntimeError, match="LLM unavailable"):
        service.generate(request)