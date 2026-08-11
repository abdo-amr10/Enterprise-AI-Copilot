from src.application.services.text_to_sql.prompt_service import PromptService
from src.application.services.text_to_sql.sql_generation_service import (
    SQLGenerationService,
)
from src.infrastructure.llm.model_config import QWEN_CONFIG
from src.infrastructure.llm.ollama_client import OllamaClient


def test_prompt_to_sql_generation():
    """Verify the complete PromptService to LLM generation flow."""

    question = "Show all customers."
    semantic_context = """
    Entity: Customer
    Table: customers
    Primary Key: customer_id
    """
    current_date = "2026-08-12"

    prompt_service = PromptService()

    request = prompt_service.build_request(
        question=question,
        semantic_context=semantic_context,
        current_date=current_date,
    )

    llm_client = OllamaClient(QWEN_CONFIG)
    generation_service = SQLGenerationService(llm_client)

    response = generation_service.generate(request)

    assert response.text.strip()