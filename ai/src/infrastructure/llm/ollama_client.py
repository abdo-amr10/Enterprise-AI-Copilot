import os

from ollama import Client

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.ports.llm_client import LLMClient
from src.infrastructure.llm.model_config import ModelConfig




class OllamaClient(LLMClient):
   """
    Provides the LLMClient implementation using the Ollama runtime.

    The client uses ModelConfig for model-specific generation settings
    and converts Ollama responses into application-level DTOs.
    """

   def __init__(self, config: ModelConfig) -> None:      
      """
        Initialize the Ollama client.

        Args:
            config: Configuration of the model used for generation.

        Raises:
             ValueError: If the configured runtime is not Ollama.    
        """
      if config.runtime != "ollama":
            raise ValueError("OllamaClient requires an Ollama runtime.")
      self._config = config
      self._host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
      self._timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
      self._client = Client(host=self._host, timeout=self._timeout)
      self._model_checked = False


   def generate(self, request:GenerationRequest,) -> GenerationResponse:
      """
        Generate text using the configured model through Ollama.

        Args:
            request: Contains the prompt to send to the model.

        Returns:
            The generated text wrapped in a GenerationResponse.
        """

      try:
         if not self._model_checked:
            self._client.show(self._config.model_name)
            self._model_checked = True
         response = self._client.generate(
            model=self._config.model_name,
            prompt=request.prompt,
            options={
               "temperature":self._config.temperature,
               "num_ctx":self._config.context_length,
               "num_predict":self._config.max_output_tokens,
            },)
      except Exception as exc:
         raise RuntimeError(
            f"Ollama at {self._host} could not serve model '{self._config.model_name}': {exc}"
         ) from exc
      
      return GenerationResponse(
         text=response["response"]
      )











