import os
import time

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

    def warmup(self) -> None:
        """Pre-load model into memory so first query has zero cold-start delay."""
        try:
            keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "-1")
            self._client.generate(
                model=self._config.model_name,
                prompt="",
                keep_alive=keep_alive,
            )
            self._model_checked = True
        except Exception:
            pass

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

            gen_kwargs = {
                "model": self._config.model_name,
                "prompt": request.prompt,
                "options": {
                    "temperature": self._config.temperature,
                    "num_ctx": self._config.context_length,
                    "num_predict": self._config.max_output_tokens,
                },
                "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "-1"),
            }
            if request.format is not None:
                gen_kwargs["format"] = request.format

            t_start = time.perf_counter()
            response = self._client.generate(**gen_kwargs)
            client_dur_ms = (time.perf_counter() - t_start) * 1000.0

            try:
                from src.observability.latency_audit import record_llm_call
                from src.observability.audit_context import get_current_audit

                ctx = get_current_audit()
                current_stage = (
                    ctx.span_stack[-1][0]
                    if (ctx and ctx.span_stack)
                    else (ctx.final_stage if ctx else "llm_generation")
                )
                est_tokens = max(1, len(request.prompt.split()) * 4 // 3)
                record_llm_call(
                    stage_name=current_stage,
                    model=self._config.model_name,
                    config_name=getattr(self._config, "runtime", "ollama"),
                    options_sent=dict(gen_kwargs.get("options", {})),
                    raw_response=response,
                    client_duration_ms=client_dur_ms,
                    estimated_prompt_tokens=est_tokens,
                )
            except Exception:
                pass
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











