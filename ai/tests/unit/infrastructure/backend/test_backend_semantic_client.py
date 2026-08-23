from src.infrastructure.backend.backend_semantic_client import BackendSemanticClient


def test_load_generation_sources_normalizes_backend_optional_source_names(monkeypatch):
    monkeypatch.setenv("BACKEND_API_BASE_URL", "http://backend.test")
    monkeypatch.setenv("BACKEND_SERVICE_BEARER_TOKEN", "test-token")
    client = BackendSemanticClient()
    responses = {
        "/api/v1/semantic-layer/files/schema-id": {
            "content": {"tables": [], "relationships": []}
        },
        "/api/v1/semantic-layer/files/docs-id": {"content": "Documentation"},
        "/api/v1/semantic-layer/files/glossary-id": {"content": "Glossary"},
        "/api/v1/semantic-layer/files/sample-id": {"content": {"accounts": []}},
    }
    monkeypatch.setattr(client, "_get", responses.__getitem__)

    sources = client.load_generation_sources(
        {
            "schema": "schema-id",
            "documentation": "docs-id",
            "glossary": "glossary-id",
            "sampleData": "sample-id",
        }
    )

    assert sources == {
        "schema": {"tables": [], "relationships": []},
        "relationships": [],
        "documentation": "Documentation",
        "business_glossary": "Glossary",
        "sample_data": {"accounts": []},
    }
    assert "glossary" not in sources
    assert "sampleData" not in sources
