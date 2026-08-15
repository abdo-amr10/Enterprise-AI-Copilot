from dataclasses import dataclass


@dataclass(frozen=True)
class BackendConfig:
    """Stores configuration required to communicate with the Backend."""

    base_url: str
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        """Validate Backend configuration."""

        if not self.base_url.strip():
            raise ValueError("base_url cannot be empty.")

        if self.timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero."
            )