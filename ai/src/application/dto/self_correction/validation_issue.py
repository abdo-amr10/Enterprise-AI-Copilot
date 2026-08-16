"""A single validation issue raised against a candidate SQL query."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationIssue:
    """Represents one concrete problem found in a SQL query.

    Instances are produced either by a deterministic validator
    (syntax, schema, or relationship) or by the LLM critic after its
    findings have passed through the CriticFindingVerifier. The
    correction prompt is built exclusively from these structured
    issues rather than free-form LLM text.
    """

    type: str
    message: str
    source: str

    def __post_init__(self) -> None:
        if not self.type.strip():
            raise ValueError("type cannot be empty.")
        if not self.message.strip():
            raise ValueError("message cannot be empty.")
        if not self.source.strip():
            raise ValueError("source cannot be empty.")
