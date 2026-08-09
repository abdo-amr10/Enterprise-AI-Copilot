"""Application boundary for reading the source database schema."""
from typing import Any, Protocol


class SchemaRepository(Protocol):
    def load(self) -> dict[str, Any]:
        """Return the source schema for the dataset-loading/build phase."""
        ...
