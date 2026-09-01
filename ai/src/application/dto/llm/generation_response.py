from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationResponse:
    """Represents the result returned by an LLM generation operation.

    This DTO provides a stable application-level representation of
    generated text without exposing runtime-specific response objects.
    """
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    model_name: str | None = None
    provider: str | None = None
    duration_ms: float | None = None

    def __post_init__(self) -> None:
        """Validate the generation response."""
        if not self.text.strip():
            raise ValueError("Generated text cannot be empty.")