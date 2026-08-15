from dataclasses import dataclass
from typing import Optional

from src.application.dto.backend.semantic_layer.source_file import SourceFile


@dataclass(frozen=True)
class UploadSourcesResponse:
    """Represents the Backend response after uploading Semantic Layer sources."""

    status: str
    semantic_layer_id: str
    name: str
    description: Optional[str]
    sources: dict[str, Optional[SourceFile]]

    def __post_init__(self) -> None:
        """Validate the uploaded Semantic Layer source response."""

        if not self.status.strip():
            raise ValueError("status cannot be empty.")

        if not self.semantic_layer_id.strip():
            raise ValueError("semantic_layer_id cannot be empty.")

        if not self.name.strip():
            raise ValueError("name cannot be empty.")