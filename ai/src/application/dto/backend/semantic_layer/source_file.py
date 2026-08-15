from dataclasses import dataclass


@dataclass(frozen=True)
class SourceFile:
    """Represents a Semantic Layer source file managed by the Backend."""

    file_id: str
    file_type: str

    def __post_init__(self) -> None:
        """Validate the source file metadata."""

        if not self.file_id.strip():
            raise ValueError("file_id cannot be empty.")

        if not self.file_type.strip():
            raise ValueError("file_type cannot be empty.")