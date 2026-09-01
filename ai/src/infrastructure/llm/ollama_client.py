import os

from ollama import Client

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.ports.llm_client import LLMClient
from src.infrastructure.llm.model_config import ModelConfig




class OllamaClient(LLMClient):
    """Provides the LLMClient implementation using the Ollama runtime.

    Uses ModelConfig for model-specific generation settings and converts Ollama
    HTTP responses into application-level GenerationResponse DTOs.
    """

    def __init__(self, config: ModelConfig) -> None:
        """Initialize the Ollama client.

        Args:
            config: Configuration of the model used for generation.

        Raises:
            ValueError: If the configured runtime is not Ollama.
        """
        if config.runtime != "ollama":
            raise ValueError("OllamaClient requires an Ollama runtime.")
        self._config = config
        self._host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
        self._timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "3000"))
        self._client = Client(host=self._host, timeout=self._timeout)
        self._model_checked = False

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate text using the configured model through Ollama.

        Args:
            request: Contains the prompt to send to the model.

        Returns:
            The generated text wrapped in a GenerationResponse.

        Raises:
            RuntimeError: If Ollama cannot be reached or the model fails to execute.
        """
        try:
            if not self._model_checked:
                self._client.show(self._config.model_name)
                self._model_checked = True
            response = self._client.generate(
                model=self._config.model_name,
                prompt=request.prompt,
                options={
                    "temperature": self._config.temperature,
                    "num_ctx": self._config.context_length,
                    "num_predict": self._config.max_output_tokens,
                },
            )
        except Exception as exc:
            raise RuntimeError(
                f"Ollama at {self._host} could not serve model '{self._config.model_name}': {exc}"
            ) from exc

        # Extract real token metrics from Ollama response
        prompt_tokens = response.get("prompt_eval_count") if isinstance(response, dict) else getattr(response, "prompt_eval_count", None)
        eval_tokens = response.get("eval_count") if isinstance(response, dict) else getattr(response, "eval_count", None)

        text = response.get("response", "") if isinstance(response, dict) else getattr(response, "response", "")

        # Robust heuristic fallback if Ollama does not report token counts
        if prompt_tokens is None:
            prompt_tokens = max(1, len(request.prompt.split()) * 4 // 3)
        if eval_tokens is None:
            eval_tokens = max(1, len(text.split()) * 4 // 3)
        total_tokens = prompt_tokens + eval_tokens

        total_duration_ns = response.get("total_duration") if isinstance(response, dict) else getattr(response, "total_duration", None)
        duration_ms = float(total_duration_ns) / 1_000_000.0 if total_duration_ns else None

        return GenerationResponse(
            text=text,
            input_tokens=int(prompt_tokens),
            output_tokens=int(eval_tokens),
            total_tokens=int(total_tokens),
            model_name=self._config.model_name,
            provider="ollama",
            duration_ms=duration_ms,
        )











