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


def test_allows_local_https_only_when_explicitly_configured(monkeypatch):
    monkeypatch.setenv("BACKEND_API_BASE_URL", "https://localhost:7031")
    monkeypatch.setenv("BACKEND_SERVICE_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("BACKEND_ALLOW_INSECURE_LOCAL_HTTPS", "true")

    client = BackendSemanticClient()

    assert client._http_client._verify_tls is False


def test_normalizes_camel_case_relationship_fields_without_guessing_missing_columns():
    layer = {
        "entities": [
            {"name": "Customer", "mapping": "customers"},
            {"name": "Account", "mapping": "accounts"},
        ],
        "relationships": [
            {
                "name": "customers_accounts",
                "fromEntity": "Customer",
                "fromColumn": "customer_id",
                "toEntity": "Account",
                "toColumn": "customer_id",
            },
            {"name": "incomplete", "fromTable": "customers", "toTable": "accounts"},
        ],
    }

    BackendSemanticClient._normalize_relationships(layer)

    assert layer["relationships"][0]["from_table"] == "customers"
    assert layer["relationships"][0]["to_table"] == "accounts"
    assert layer["relationships"][0]["from_column"] == "customer_id"
    assert "from_column" not in layer["relationships"][1]
