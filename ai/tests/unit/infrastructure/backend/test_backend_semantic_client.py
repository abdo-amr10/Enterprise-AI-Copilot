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


def test_auto_login_with_email_and_password(monkeypatch):
    monkeypatch.setenv("BACKEND_API_BASE_URL", "http://backend.test")
    monkeypatch.delenv("BACKEND_SERVICE_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("BACKEND_SERVICE_EMAIL", "admin@example.com")
    monkeypatch.setenv("BACKEND_SERVICE_PASSWORD", "secret123")

    login_called = False

    def fake_post(url, **kwargs):
        nonlocal login_called
        if "/api/v1/Auth/login" in url:
            login_called = True
            class MockResponse:
                status_code = 200
                def raise_for_status(self): pass
                def json(self): return {"token": "auto-generated-token"}
            return MockResponse()
        raise NotImplementedError(url)

    monkeypatch.setattr("requests.post", fake_post)

    client = BackendSemanticClient()
    assert client._http_client._token == "auto-generated-token"
    assert login_called is True


def test_get_status_uses_short_ttl_cache_to_avoid_duplicate_calls(monkeypatch):
    monkeypatch.setenv("BACKEND_API_BASE_URL", "http://backend.test")
    monkeypatch.setenv("BACKEND_SERVICE_BEARER_TOKEN", "test-token")
    client = BackendSemanticClient()

    call_count = 0

    def mock_get(path):
        nonlocal call_count
        call_count += 1
        return {"status": "Approved", "revisionId": "REV-1"}

    monkeypatch.setattr(client, "_get", mock_get)

    # First call: hits network
    res1 = client.get_status()
    assert res1["revisionId"] == "REV-1"
    assert call_count == 1

    # Second call immediately after: hits TTL cache, no network call!
    res2 = client.get_status()
    assert res2 == res1
    assert call_count == 1

    # Force bypasses cache
    res3 = client.get_status(force=True)
    assert res3 == res1
    assert call_count == 2


