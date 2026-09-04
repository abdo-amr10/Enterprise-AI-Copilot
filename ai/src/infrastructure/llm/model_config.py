import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    """
    Holds the configuration required to interact with the selected LLM.

    The class is intentionally limited to model configuration.
    Model loading and inference are handled by the infrastructure client.
    """
    model_name: str
    runtime: str
    temperature: float
    context_length: int
    max_output_tokens: int

    def __post_init__(self) -> None:
        """Validate model configuration values at initialization."""
        if not self.model_name.strip():
            raise ValueError("model_name cannot be empty.")
        if not self.runtime.strip():
            raise ValueError("runtime cannot be empty.")
        if self.temperature < 0:
            raise ValueError("temperature cannot be negative.")
        if self.context_length <= 0:
            raise ValueError("context_length must be greater than zero.")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than zero.")
        if self.max_output_tokens > self.context_length:
            raise ValueError("max_output_tokens cannot exceed context_length.")


_DEFAULT_MODEL = os.getenv("LLM_MODEL_NAME", "qwen2.5-coder:7b")

# Text-to-SQL: prompt + semantic context + output must fit comfortably.
_DEFAULT_CTX = int(os.getenv("LLM_CONTEXT_LENGTH", "8192"))
_DEFAULT_MAX_OUTPUT = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1024"))

# Semantic relationship discovery may receive substantially larger schemas.
_SEMANTIC_CTX = int(os.getenv("LLM_SEMANTIC_CONTEXT_LENGTH", "16384"))
_SEMANTIC_MAX_OUTPUT = int( os.getenv("LLM_SEMANTIC_MAX_OUTPUT_TOKENS", "4096"))


QWEN_CONFIG = ModelConfig(
    model_name=_DEFAULT_MODEL,
    runtime="ollama",
    temperature=0.0,
    context_length=_DEFAULT_CTX,
    max_output_tokens=min(_DEFAULT_MAX_OUTPUT, _DEFAULT_CTX),
)


SEMANTIC_LAYER_CONFIG = ModelConfig(
    model_name=_DEFAULT_MODEL,
    runtime="ollama",
    temperature=0.3,
    context_length=_SEMANTIC_CTX,
    max_output_tokens=min(_SEMANTIC_MAX_OUTPUT, _SEMANTIC_CTX),
)


SQL_CRITIC_CONFIG = ModelConfig(
    model_name=_DEFAULT_MODEL,
    runtime="ollama",
    temperature=0.0,
    context_length=_DEFAULT_CTX,
    max_output_tokens=min(512, _DEFAULT_CTX),
)


SQL_CORRECTION_CONFIG = ModelConfig(
    model_name=_DEFAULT_MODEL,
    runtime="ollama",
    temperature=0.0,
    context_length=_DEFAULT_CTX,
    max_output_tokens=min(512, _DEFAULT_CTX),
)