"""Policy settings for formatting Backend execution results."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PostQueryResponseSettings:
    max_inline_rows: int = 100

    def __post_init__(self) -> None:
        if self.max_inline_rows < 1:
            raise ValueError("max_inline_rows must be positive.")
