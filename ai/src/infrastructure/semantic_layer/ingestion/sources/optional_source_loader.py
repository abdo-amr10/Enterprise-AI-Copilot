"""Load optional semantic-layer source documents during ingestion."""

from pathlib import Path
from typing import Any


class OptionalSourceLoader:
    """Loads available optional source documents without requiring them.

    The loader reads optional documentation and business-glossary sources
    when they are available. Missing optional sources are represented as
    absent values and do not cause ingestion to fail.

    The loader does not interpret, generate, or modify semantic content.
    AI-assisted enrichment and human review happen in later stages.

    Input:
        Source paths for optional documentation and business-glossary files.

    Output:
        A dictionary containing the available source contents. Missing
        optional sources are represented by ``None``.
    """

    def load(
        self,
        documentation_path: str | Path | None = None,
        business_glossary_path: str | Path | None = None,
    ) -> dict[str, str | None]:
        """Load the available optional source documents.

        Args:
            documentation_path: Path to the optional documentation file.
            business_glossary_path: Path to the optional business glossary.

        Returns:
            A dictionary containing the loaded source contents. A source
            that is not provided or does not exist is returned as ``None``.
        """
        return {
            "documentation": self._read_optional(documentation_path),
            "business_glossary": self._read_optional(business_glossary_path),
        }

    @staticmethod
    def _read_optional(path: str | Path | None) -> str | None:
        """Read an optional text source if it is available.

        Args:
            path: Optional path to the source file.

        Returns:
            The file content, or ``None`` when no source is available.
        """
        if path is None:
            return None

        source_path = Path(path)

        if not source_path.exists():
            return None

        return source_path.read_text(encoding="utf-8")