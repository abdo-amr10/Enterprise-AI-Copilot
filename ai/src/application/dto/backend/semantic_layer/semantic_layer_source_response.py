from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticLayerSourceResponse:
    """Represents a source file retrieved from the Backend."""

    file_id: str
    file_name: str
    file_type: str
    content: str

    def __post_init__(self) -> None:
        """Validate the source file response."""

        if not self.file_id.strip():
            raise ValueError("file_id cannot be empty.")

        if not self.file_name.strip():
            raise ValueError("file_name cannot be empty.")

        if not self.file_type.strip():
            raise ValueError("file_type cannot be empty.")

        if not self.content.strip():
            raise ValueError("content cannot be empty.")