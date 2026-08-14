from typing import Protocol

from ai.src.application.dto.llm.generation_request import GenerationRequest
from ai.src.application.dto.llm.generation_response import GenerationResponse



class LLMClient(Protocol):
     """
    Defines the application-level contract for LLM text generation.

    The application depends on this abstraction instead of depending
    on a specific LLM provider, model, or runtime.
    """

     def generate(self,request:GenerationRequest,) -> GenerationResponse:
      """
        Generate a response from the provided LLM generation request.

        Args:
            request: Contains the prompt and optional generation parameters.

        Returns:
            The generated LLM response.
        """
      ...