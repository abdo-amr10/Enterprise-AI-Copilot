import logging
import os
import time

from ollama import Client

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.ports.llm_client import LLMClient
from src.infrastructure.llm.model_config import ModelConfig


logger = logging.getLogger(__name__)


def _parse_keep_alive(val: str | None) -> int | str:
    """Parse Ollama keep_alive configuration.

    Supported values:
        - "-1" / -1  -> keep model loaded indefinitely
        - "0" / 0    -> unload model immediately after generation
        - "15m"       -> keep model loaded for 15 minutes
        - "1h"        -> keep model loaded for 1 hour

    Duration strings are passed directly to Ollama.
    Integer values are converted to int.
    """
    if not val:
        return "15m"

    val = val.strip()

    try:
        return int(val)
    except ValueError:
        return val


class OllamaClient(LLMClient):
    """LLMClient implementation using the local Ollama runtime.

    Uses ModelConfig for model-specific generation settings and converts
    Ollama responses into application-level GenerationResponse DTOs.
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

        self._host = os.getenv(
            "OLLAMA_HOST",
            "http://127.0.0.1:11434",
        )

        self._timeout = float(
            os.getenv(
                "OLLAMA_TIMEOUT_SECONDS",
                "3000",
            )
        )

        # Configurable per developer/team environment.
        # Example:
        #   OLLAMA_KEEP_ALIVE=15m
        #   OLLAMA_KEEP_ALIVE=-1
        #   OLLAMA_KEEP_ALIVE=1h
        self._keep_alive = _parse_keep_alive(
            os.getenv("OLLAMA_KEEP_ALIVE", "15m")
        )

        self._client = Client(
            host=self._host,
            timeout=self._timeout,
        )

        self._model_checked = False

        logger.info(
            "OllamaClient initialized | host=%s | model=%s | "
            "keep_alive=%s | timeout=%ss",
            self._host,
            self._config.model_name,
            self._keep_alive,
            self._timeout,
        )

    def warmup(self) -> None:
        """Pre-load the model into memory.

        This reduces cold-start latency for the first real request.

        The model remains loaded according to the configured keep_alive value.
        """
        try:
            self._client.generate(
                model=self._config.model_name,
                prompt="",
                keep_alive=self._keep_alive,
            )

            self._model_checked = True

            logger.info(
                "Ollama model warmed up successfully | model=%s | "
                "keep_alive=%s",
                self._config.model_name,
                self._keep_alive,
            )

        except Exception as exc:
            logger.warning(
                "Ollama warmup failed | model=%s | error=%s",
                self._config.model_name,
                exc,
            )

    def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResponse:
        """Generate text using the configured Ollama model.

        Args:
            request: Contains the prompt to send to the model.

        Returns:
            Generated text wrapped in a GenerationResponse.

        Raises:
            RuntimeError:
                If Ollama cannot be reached or the model fails to execute.
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
                "keep_alive": self._keep_alive,
            }

            if request.format is not None:
                gen_kwargs["format"] = request.format

            t_start_ns = time.perf_counter_ns()
            t_start = time.perf_counter()

            response = self._client.generate(**gen_kwargs)

            t_end_ns = time.perf_counter_ns()
            client_dur_ms = (t_end_ns - t_start_ns) / 1_000_000.0

            # Observability / latency audit
            try:
                from src.observability.audit_context import (
                    get_current_audit,
                )
                from src.observability.latency_audit import (
                    record_llm_call,
                )

                ctx = get_current_audit()

                current_stage = (
                    ctx.span_stack[-1][0]
                    if (ctx and ctx.span_stack)
                    else (
                        ctx.final_stage
                        if ctx
                        else "llm_generation"
                    )
                )

                estimated_prompt_tokens = max(
                    1,
                    len(request.prompt.split()) * 4 // 3,
                )

                record_llm_call(
                    stage_name=current_stage,
                    model=self._config.model_name,
                    config_name=getattr(
                        self._config,
                        "runtime",
                        "ollama",
                    ),
                    options_sent=dict(
                        gen_kwargs.get("options", {})
                    ),
                    raw_response=response,
                    client_duration_ms=client_dur_ms,
                    estimated_prompt_tokens=estimated_prompt_tokens,
                )

            except Exception as exc:
                # Observability failure should never break LLM generation.
                logger.debug(
                    "Failed to record Ollama latency audit: %s",
                    exc,
                )

        except Exception as exc:
            raise RuntimeError(
                f"Ollama at {self._host} could not serve model "
                f"'{self._config.model_name}': {exc}"
            ) from exc

        # ---------------------------------------------------------
        # Extract token metrics from Ollama response
        # ---------------------------------------------------------

        if isinstance(response, dict):
            prompt_tokens = response.get("prompt_eval_count")
            eval_tokens = response.get("eval_count")
            text = response.get("response", "")
            total_duration_ns = response.get("total_duration")
            load_duration_ns = response.get("load_duration")
            prompt_eval_ns = response.get("prompt_eval_duration")
            eval_ns = response.get("eval_duration")
        else:
            prompt_tokens = getattr(response, "prompt_eval_count", None)
            eval_tokens = getattr(response, "eval_count", None)
            text = getattr(response, "response", "")
            total_duration_ns = getattr(response, "total_duration", None)
            load_duration_ns = getattr(response, "load_duration", None)
            prompt_eval_ns = getattr(response, "prompt_eval_duration", None)
            eval_ns = getattr(response, "eval_duration", None)

        # ---------------------------------------------------------
        # Token fallback
        # ---------------------------------------------------------

        if prompt_tokens is None:
            prompt_tokens = max(
                1,
                len(request.prompt.split()) * 4 // 3,
            )

        if eval_tokens is None:
            eval_tokens = max(
                1,
                len(text.split()) * 4 // 3,
            )

        total_tokens = prompt_tokens + eval_tokens

        # ---------------------------------------------------------
        # Duration & Evidence-Based Lifecycle
        # ---------------------------------------------------------

        duration_ms = (
            float(total_duration_ns) / 1_000_000.0
            if total_duration_ns
            else None
        )

        model_load_duration_ms = (
            float(load_duration_ns) / 1_000_000.0
            if load_duration_ns is not None
            else 0.0
        )

        server_eval_ns = (
            (prompt_eval_ns or 0) + (eval_ns or 0)
            if (prompt_eval_ns is not None or eval_ns is not None)
            else None
        )
        server_duration_ms = (
            float(server_eval_ns) / 1_000_000.0
            if server_eval_ns is not None
            else None
        )

        client_overhead_ms = max(
            0.0,
            client_dur_ms - ((server_duration_ms or 0.0) + model_load_duration_ms),
        )

        if load_duration_ns is None:
            model_load_type = "none"
            cold_load = None
        elif model_load_duration_ms == 0.0:
            model_load_type = "warm"
            cold_load = False
        else:
            model_load_type = "cold"
            cold_load = True

        if load_duration_ns is not None:
            logger.info(
                "Ollama generation | model=%s | "
                "load=%.2fms | server=%.2fms | client=%.2fms | "
                "overhead=%.2fms | prompt_tokens=%s | output_tokens=%s",
                self._config.model_name,
                model_load_duration_ms,
                server_duration_ms or 0.0,
                client_dur_ms,
                client_overhead_ms,
                prompt_tokens,
                eval_tokens,
            )

        return GenerationResponse(
            text=text,
            input_tokens=int(prompt_tokens),
            output_tokens=int(eval_tokens),
            total_tokens=int(total_tokens),
            model_name=self._config.model_name,
            provider="ollama",
            duration_ms=duration_ms,
            server_duration_ms=server_duration_ms,
            client_duration_ms=client_dur_ms,
            client_overhead_ms=client_overhead_ms,
            model_load_duration_ms=model_load_duration_ms,
            model_load_type=model_load_type,
            cold_load=cold_load,
        )