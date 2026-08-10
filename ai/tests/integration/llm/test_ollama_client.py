from src.application.dto.generation_request import GenerationRequest
from src.application.dto.generation_response import GenerationResponse
from src.infrastructure.llm.model_config import QWEN_CONFIG
from src.infrastructure.llm.ollama_client import OllamaClient


def test_qwen_genration_through_ollama():
   client = OllamaClient(QWEN_CONFIG)

   request = GenerationRequest(prompt="Return only this SQL query: SELECT 1;")
   response = client.generate(request)

   assert isinstance(response, GenerationResponse)
   assert response.text
   assert isinstance(response.text,str)
