from pathlib import Path

from src.infrastructure.semantic_layer.ingestion.sources.optional_source_loader import (
    OptionalSourceLoader,
)


class TestOptionalSourceLoader:
    """Unit tests for loading optional semantic-layer sources."""

    def test_load_reads_available_optional_sources(
        self,
        tmp_path: Path,
    ) -> None:
        """Verify that available documentation and glossary files are loaded."""

        documentation = tmp_path / "documentation.md"
        glossary = tmp_path / "business_glossary.md"

        documentation.write_text(
            "# Database Documentation\nCustomer information.",
            encoding="utf-8",
        )
        glossary.write_text(
            "# Business Glossary\nCustomer: account holder.",
            encoding="utf-8",
        )

        result = OptionalSourceLoader().load(
            documentation_path=documentation,
            business_glossary_path=glossary,
        )

        assert result["documentation"] == (
            "# Database Documentation\nCustomer information."
        )
        assert result["business_glossary"] == (
            "# Business Glossary\nCustomer: account holder."
        )

    def test_load_returns_none_for_missing_optional_sources(
        self,
        tmp_path: Path,
    ) -> None:
        """Verify that missing optional sources do not fail ingestion."""

        result = OptionalSourceLoader().load(
            documentation_path=tmp_path / "missing_documentation.md",
            business_glossary_path=tmp_path / "missing_glossary.md",
        )

        assert result["documentation"] is None
        assert result["business_glossary"] is None

    def test_load_allows_sources_to_be_omitted(self) -> None:
        """Verify that ingestion works when no optional sources are provided."""

        result = OptionalSourceLoader().load()

        assert result == {
            "documentation": None,
            "business_glossary": None,
        }