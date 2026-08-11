"""Defines the input contract for semantic-layer construction."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SemanticLayerBuildInput:
    """Input data required to build an initial semantic layer.

    Required:
        schema: Normalized database schema metadata.
        relationships: Validated database relationship metadata.

    Optional:
        documentation: Additional database documentation, if available.
        business_glossary: Business terminology and semantic definitions,
            if available.
        sample_data: Synthetic sample records, if available.

    Returns:
        A validated, immutable data object representing the inputs
        available to the semantic-layer builder.
    """

    schema: dict[str, Any]
    relationships: list[dict[str, Any]]
    documentation: str | None = None
    business_glossary: str | None = None
    sample_data: dict[str, Any] | None = None