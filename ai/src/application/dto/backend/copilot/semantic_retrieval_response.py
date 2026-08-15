"""Internal response contract for the semantic retrieval API."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticRetrievalResponse:
    status: str
    tables: tuple[str, ...]
    business_rules: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "context": {
                "tables": list(self.tables),
                "businessRules": list(self.business_rules),
            },
        }
