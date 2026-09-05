from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class GenerationRequest:
    """
    Represents the input required for an LLM generation operation.

    This DTO carries request-specific generation data from the
    application layer to the LLM abstraction.
    """
    prompt: str
    format: str | None = None
    response_model: Any = None
    
    def __post_init__(self) -> None:
        """Validate the generation request."""

        if not self.prompt.strip():
            raise ValueError("prompt cannot be empty.")
