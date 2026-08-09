"""Infrastructure adapter for replacing the active semantic-layer snapshot."""
import shutil
from pathlib import Path


class SemanticLayerLoader:
    """Atomically replaces the active semantic-layer directory."""

    REQUIRED_FILES = (
        "entities/entities.json",
        "relationships/relationships.json",
        "measures/measures.json",
        "dimensions/dimensions.json",
        "business_rules/business_rules.json",
        "metadata/metadata.json",
    )

    def __init__(self, active_root: str | Path) -> None:
        self._active_root = Path(active_root)

    def replace(self, source_root: str | Path) -> None:
        source = Path(source_root)
        self._validate_source(source)

        temporary = self._temporary_path()
        if temporary.exists():
            shutil.rmtree(temporary)

        shutil.copytree(source, temporary)

        if self._active_root.exists():
            shutil.rmtree(self._active_root)

        temporary.rename(self._active_root)

    def _validate_source(self, source: Path) -> None:
        missing = [
            file_path
            for file_path in self.REQUIRED_FILES
            if not (source / file_path).exists()
        ]

        if missing:
            raise FileNotFoundError(f"Missing semantic artifacts: {missing}")

    def _temporary_path(self) -> Path:
        return self._active_root.with_name(
            f"{self._active_root.name}.tmp"
        )
