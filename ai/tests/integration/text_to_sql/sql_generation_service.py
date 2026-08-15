import pytest

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.services.text_to_sql.sql_generation_service import (
    SQLGenerationService,
)
from src.infrastructure.llm.model_config import QWEN_CONFIG
from src.infrastructure.llm.ollama_client import OllamaClient


@pytest.mark.integration
def test_sql_generation_with_ollama():
    """Verify SQL generation through the real Ollama client."""

    request = GenerationRequest(
        prompt="Generate a SQL query that returns all customers."
    )

    llm_client = OllamaClient(QWEN_CONFIG)
    service = SQLGenerationService(llm_client)

    response = service.generate(request)

    assert response.text.strip()
