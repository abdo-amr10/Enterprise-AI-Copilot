from src.application.dto.generation_request import GenerationRequest
from src.application.dto.generation_response import GenerationResponse
from src.application.ports.llm_client import LLMClient



class SQLGenerationService:
    """
    Application service responsible for orchestrating SQL generation.

    The service delegates LLM generation to the LLMClient abstraction
    and does not depend on any specific LLM provider or runtime.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """
        Generate a response using the configured LLM client.

        Args:
            request: Validated generation request containing the prompt.

        Returns:
            The generated LLM response.
        """
        return self._llm_client.generate(request)