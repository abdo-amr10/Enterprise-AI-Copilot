from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    """
    Holds the configuration required to interact with the selected LLM.

    The class is intentionally limited to model configuration.
    Model loading and inference are handled by the infrastructure client.
    """
    model_name: str
    runtime:str
    temperature:float
    context_length:int
    max_output_tokens:int

    def __post_init__(self)->None:
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



QWEN_CONFIG =ModelConfig(
    model_name="qwen2.5-coder:7b",
    runtime="ollama",
    temperature=0.0,
    # Keep below the 32k setting that exhausts local resources, while leaving
    # enough room for multi-CTE analytical SQL and its JSON wrapper.
    context_length=12288,
    max_output_tokens=2048
)

SEMANTIC_LAYER_CONFIG = ModelConfig(
    model_name="qwen2.5-coder:7b",
    runtime="ollama",
    temperature=0.3,
    context_length=32768,
    max_output_tokens=12288,
)

SQL_CRITIC_CONFIG = ModelConfig(
    model_name="qwen2.5-coder:7b",
    runtime="ollama",
    temperature=0.0,
    context_length=32768,
    max_output_tokens=1024,
)

SQL_CORRECTION_CONFIG = ModelConfig(
    model_name="qwen2.5-coder:7b",
    runtime="ollama",
    temperature=0.0,
    context_length=32768,
    max_output_tokens=2048,
)
