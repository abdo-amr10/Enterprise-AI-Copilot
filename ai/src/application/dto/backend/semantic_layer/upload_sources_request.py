from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UploadSourcesRequest:
    """Represents the source files uploaded for a Semantic Layer."""

    name: str
    description: Optional[str]
    schema_file: str
    documentation_file: Optional[str]
    glossary_file: Optional[str]
    sample_data_file: Optional[str]

    def __post_init__(self) -> None:
        """Validate the uploaded Semantic Layer source request."""

        if not self.name.strip():
            raise ValueError("name cannot be empty.")

        if not self.schema_file.strip():
            raise ValueError("schema_file cannot be empty.")

        if self.description is not None and not self.description.strip():
            raise ValueError("description cannot be empty when provided.")

        if (
            self.documentation_file is not None
            and not self.documentation_file.strip()
        ):
            raise ValueError(
                "documentation_file cannot be empty when provided."
            )

        if self.glossary_file is not None and not self.glossary_file.strip():
            raise ValueError(
                "glossary_file cannot be empty when provided."
            )

        if (
            self.sample_data_file is not None
            and not self.sample_data_file.strip()
        ):
            raise ValueError(
                "sample_data_file cannot be empty when provided."
            )