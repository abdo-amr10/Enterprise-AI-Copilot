from src.api import dependencies
from src.infrastructure.semantic_layer.ingestion.database_schema_provider import (
    DatabaseSchemaProvider,
)
from src.infrastructure.semantic_layer.retrieval.file_semantic_repository import (
    FileSemanticRepository,
)


def test_local_development_mode_is_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("AI_LOCAL_DEV_MODE", raising=False)
    assert dependencies.is_local_development_mode() is False

    monkeypatch.setenv("AI_LOCAL_DEV_MODE", "true")
    assert dependencies.is_local_development_mode() is True


def test_local_development_mode_uses_local_adapters(monkeypatch) -> None:
    monkeypatch.setenv("AI_LOCAL_DEV_MODE", "true")
    monkeypatch.setattr(dependencies, "_semantic_repository", None)

    assert isinstance(dependencies.get_semantic_repository(), FileSemanticRepository)
    assert isinstance(dependencies.get_schema_provider(), DatabaseSchemaProvider)
