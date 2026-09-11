"""Comprehensive tests for semantic index persistence, FAISS bundle alignment, and zero-request hot path."""
import io
import json
import threading
import zipfile
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from src.config.semantic_settings import SemanticSettings
from src.infrastructure.backend.backend_http_client import BackendHttpClient
from src.infrastructure.backend.backend_semantic_client import BackendSemanticClient
from src.infrastructure.semantic_layer.ingestion.backend_database_schema_provider import (
    BackendDatabaseSchemaProvider,
)
from src.infrastructure.semantic_layer.retrieval.backend_semantic_repository import (
    BackendSemanticRepository,
)
from src.infrastructure.semantic_layer.retrieval.faiss_vector_index import FaissVectorIndex


class MockEmbeddingService:
    model_name = "all-MiniLM-L6-v2"
    model_version = "1.0.0"
    embedding_dimension = 4
    device = "cpu"

    def __init__(self):
        self.encode_doc_calls = 0
        self.encode_query_calls = 0

    def encode_documents(self, texts):
        self.encode_doc_calls += 1
        vectors = []
        for i in range(len(texts)):
            v = np.zeros(self.embedding_dimension, dtype=np.float32)
            v[i % self.embedding_dimension] = 1.0
            vectors.append(v)
        return np.vstack(vectors)

    def encode_query(self, query):
        self.encode_query_calls += 1
        v = np.zeros(self.embedding_dimension, dtype=np.float32)
        v[0] = 1.0
        return v


def _create_sample_zip(revision_id="rev-100", layer_id="layer-100", dim=4, doc_count=2):
    import faiss
    index = faiss.IndexFlatIP(dim)
    vectors = np.zeros((doc_count, dim), dtype=np.float32)
    for i in range(doc_count):
        vectors[i, i % dim] = 1.0
    index.add(vectors)
    faiss_bytes = bytes(faiss.serialize_index(index))

    index_meta = {
        "index_version": "1.0.0",
        "semantic_layer_id": layer_id,
        "revision_id": revision_id,
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dimension": dim,
        "document_count": doc_count,
        "similarity_metric": "cosine",
        "index_type": "faiss.IndexFlatIP",
    }
    doc_meta = [
        {
            "id": f"{layer_id}:{revision_id}:entity:customer",
            "name": "Customer",
            "type": "entity",
            "object_type": "entity",
            "text": "Entity Customer table customers",
            "payload": {"name": "Customer"},
        },
        {
            "id": f"{layer_id}:{revision_id}:entity:order",
            "name": "Order",
            "type": "entity",
            "object_type": "entity",
            "text": "Entity Order table orders",
            "payload": {"name": "Order"},
        },
    ]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("semantic_index.faiss", faiss_bytes)
        zf.writestr("index_metadata.json", json.dumps(index_meta))
        zf.writestr("document_metadata.json", json.dumps(doc_meta))
    return buf.getvalue(), index_meta, doc_meta


def test_backend_http_client_put_multipart():
    with patch("requests.put") as mock_put:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "READY"}'
        mock_resp.json.return_value = {"status": "READY"}
        mock_put.return_value = mock_resp

        client = BackendHttpClient(base_url="http://localhost:5000", token="test-token")
        res = client.put_multipart(
            "/api/v1/test",
            data={"key": "val"},
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
        assert res == {"status": "READY"}
        assert mock_put.call_count == 1
        args, kwargs = mock_put.call_args
        assert kwargs["data"] == {"key": "val"}
        assert "file" in kwargs["files"]
        assert kwargs["headers"]["Authorization"] == "Bearer test-token"


def test_backend_semantic_client_download_and_upload():
    http_mock = MagicMock()
    client = BackendSemanticClient(http_client=http_mock)

    # 1. Download returns 200 ZIP
    http_mock.get_file.return_value = b"PK-fake-zip"
    assert client.download_index_artifact("rev-1") == b"PK-fake-zip"

    # 2. Download returns 404 -> None
    import requests
    err_404 = requests.HTTPError(response=MagicMock(status_code=404))
    http_mock.get_file.side_effect = err_404
    assert client.download_index_artifact("rev-missing") is None

    # 3. Download raises 500 -> propagates error
    err_500 = requests.HTTPError(response=MagicMock(status_code=500, text="Internal Error"))
    http_mock.get_file.side_effect = err_500
    with pytest.raises(RuntimeError) as exc_info:
        client.download_index_artifact("rev-fail")
    assert "HTTP 500" in str(exc_info.value)

    # 4. Upload succeeds on 200
    http_mock.put_multipart.return_value = {"status": "READY"}
    assert client.upload_index_artifact("rev-1", b"faiss", "{}", "[]") is True

    # 5. Upload accepts 409 Conflict as success
    err_409 = requests.HTTPError(response=MagicMock(status_code=409))
    http_mock.put_multipart.side_effect = err_409
    assert client.upload_index_artifact("rev-1", b"faiss", "{}", "[]") is True


def test_faiss_vector_index_export_and_load_from_zip():
    zip_bytes, index_meta, doc_meta = _create_sample_zip(revision_id="rev-200", dim=4, doc_count=2)
    idx = FaissVectorIndex()
    loaded_meta = idx.load_from_zip_bytes(zip_bytes, expected_revision_id="rev-200")

    assert loaded_meta["revision_id"] == "rev-200"
    assert len(idx._documents) == 2
    assert idx._documents[0]["name"] == "Customer"

    # Vector search works accurately on restored index
    results = idx.search(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32), top_k=1)
    assert len(results) == 1
    assert results[0]["name"] == "Customer"

    # Re-export and verify bundle integrity
    faiss_bytes, out_index_meta, out_doc_meta = idx.export_bundle_bytes()
    assert len(faiss_bytes) > 0
    assert json.loads(out_index_meta)["revision_id"] == "rev-200"
    assert len(json.loads(out_doc_meta)) == 2


def test_faiss_vector_index_corrupt_zip_rejection():
    idx = FaissVectorIndex()
    # Bad zip bytes
    with pytest.raises(ValueError, match="Malformed ZIP"):
        idx.load_from_zip_bytes(b"not-a-zip")

    # Missing member
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("semantic_index.faiss", b"fake")
    with pytest.raises(ValueError, match="missing required artifact files"):
        idx.load_from_zip_bytes(buf.getvalue())

    # Revision mismatch
    zip_bytes, _, _ = _create_sample_zip(revision_id="rev-actual")
    with pytest.raises(ValueError, match="Artifact revision mismatch"):
        idx.load_from_zip_bytes(zip_bytes, expected_revision_id="rev-other")


def test_repository_restores_from_backend_artifact_without_rebuilding():
    client = MagicMock()
    zip_bytes, _, _ = _create_sample_zip(revision_id="rev-300", layer_id="sl-300")
    client.get_status.return_value = {"status": "Approved", "revisionId": "rev-300"}
    client.load_revision.return_value = {
        "metadata": {"revision_id": "rev-300", "semantic_layer_id": "sl-300"},
        "entities": [], "relationships": [], "measures": [], "dimensions": [], "business_rules": [], "security_domains": [],
    }
    client.download_index_artifact.return_value = zip_bytes

    embedding = MockEmbeddingService()
    repo = BackendSemanticRepository(
        client=client,
        embedding_service=embedding,
        settings=SemanticSettings(),
    )

    assert not repo.is_ready()
    synced = repo.sync_active_index()
    assert synced is True
    assert repo.is_ready()
    assert repo.indexed_revision_id == "rev-300"
    # Crucial assertion: encode_documents was NEVER called because artifact was loaded!
    assert embedding.encode_doc_calls == 0
    assert client.download_index_artifact.call_count == 1


def test_repository_fallback_build_and_upload_on_404():
    client = MagicMock()
    client.get_status.return_value = {"status": "Approved", "revisionId": "rev-404"}
    client.load_revision.return_value = {
        "metadata": {"revision_id": "rev-404", "semantic_layer_id": "sl-404", "status": "approved"},
        "entities": [{"object_id": "e1", "name": "Entity1", "mapping": "tbl1"}],
        "relationships": [], "measures": [], "dimensions": [], "business_rules": [], "security_domains": [],
    }
    client.download_index_artifact.return_value = None  # 404 Not Found
    client.upload_index_artifact.return_value = True

    embedding = MockEmbeddingService()
    repo = BackendSemanticRepository(
        client=client,
        embedding_service=embedding,
        settings=SemanticSettings(),
    )

    synced = repo.sync_active_index()
    assert synced is True
    assert repo.is_ready()
    # On 404, local build was triggered and artifact uploaded
    assert embedding.encode_doc_calls == 1
    assert client.upload_index_artifact.call_count == 1


def test_repository_backend_error_does_not_trigger_local_rebuild():
    client = MagicMock()
    client.get_status.return_value = {"status": "Approved", "revisionId": "rev-500"}
    client.load_revision.return_value = {"metadata": {"revision_id": "rev-500", "semantic_layer_id": "sl-500"}}
    client.download_index_artifact.side_effect = RuntimeError("HTTP 500 Internal Server Error")

    embedding = MockEmbeddingService()
    repo = BackendSemanticRepository(
        client=client,
        embedding_service=embedding,
        settings=SemanticSettings(),
    )

    synced = repo.sync_active_index()
    assert synced is False
    assert not repo.is_ready()
    # On 500, we MUST NOT rebuild or upload locally!
    assert embedding.encode_doc_calls == 0
    assert client.upload_index_artifact.call_count == 0


def test_five_consecutive_questions_zero_backend_calls():
    client = MagicMock()
    zip_bytes, _, _ = _create_sample_zip(revision_id="rev-prod", layer_id="sl-prod")
    client.get_status.return_value = {"status": "Approved", "revisionId": "rev-prod"}
    client.load_revision.return_value = {
        "metadata": {"revision_id": "rev-prod", "semantic_layer_id": "sl-prod"},
        "entities": [], "relationships": [], "measures": [], "dimensions": [], "business_rules": [], "security_domains": [],
    }
    client.download_index_artifact.return_value = zip_bytes
    client.get_active_revision_schema.return_value = {"revisionId": "rev-prod", "schema": {"database": "ERP_DB", "tables": {"t1": {"columns": []}}}}

    embedding = MockEmbeddingService()
    repo = BackendSemanticRepository(
        client=client,
        embedding_service=embedding,
        settings=SemanticSettings(),
    )
    schema_provider = BackendDatabaseSchemaProvider(client=client)

    # Initial warm-up (e.g. startup / sync)
    repo.ensure_initialized()
    schema_provider.get_schema()

    # Reset call counts to test the hot path exclusively
    client.get_status.reset_mock()
    client.load_revision.reset_mock()
    client.download_index_artifact.reset_mock()
    client.upload_index_artifact.reset_mock()
    client.get_active_revision_schema.reset_mock()
    client._get.reset_mock()

    # Execute 5 consecutive user questions
    questions = [
        "Show customer list",
        "How many orders were placed yesterday?",
        "List top revenue products",
        "Find overdue accounts",
        "Display loan balance summary",
    ]

    for q in questions:
        # 1. Preflight accesses schema
        schema = schema_provider.get_schema()
        assert "tables" in schema

        # 2. Context retrieval accesses layer and vector search
        layer = repo.load()
        assert layer["metadata"]["revision_id"] == "rev-prod"

        results = repo.retrieve(q, top_k=2)
        assert len(results) > 0

        # 3. Schema validator in self-correction accesses schema
        schema_again = schema_provider.get_schema()
        assert schema_again is schema

    # VERIFY STRICTLY ZERO BACKEND HTTP CALLS ACROSS ALL 5 QUESTIONS
    assert client.get_status.call_count == 0
    assert client.load_revision.call_count == 0
    assert client.download_index_artifact.call_count == 0
    assert client.upload_index_artifact.call_count == 0
    assert client.get_active_revision_schema.call_count == 0
    assert client._get.call_count == 0


def test_concurrent_initialization_thread_safety():
    client = MagicMock()
    zip_bytes, _, _ = _create_sample_zip(revision_id="rev-conc", layer_id="sl-conc")
    client.get_status.return_value = {"status": "Approved", "revisionId": "rev-conc"}
    client.load_revision.return_value = {
        "metadata": {"revision_id": "rev-conc", "semantic_layer_id": "sl-conc"},
        "entities": [], "relationships": [], "measures": [], "dimensions": [], "business_rules": [], "security_domains": [],
    }
    client.download_index_artifact.return_value = zip_bytes

    embedding = MockEmbeddingService()
    repo = BackendSemanticRepository(
        client=client,
        embedding_service=embedding,
        settings=SemanticSettings(),
    )

    errors = []
    def worker():
        try:
            repo.ensure_initialized()
            res = repo.retrieve("test query", 1)
            assert len(res) > 0
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert repo.is_ready()
    # Download artifact called only once despite 10 concurrent threads!
    assert client.download_index_artifact.call_count == 1


def test_retrieve_and_load_disallow_cold_start_on_request_path():
    """Verify that when allow_cold_start=False (the user-request hot path), no Backend HTTP calls are made."""
    client = MagicMock()
    repo = BackendSemanticRepository(
        client=client,
        embedding_service=MockEmbeddingService(),
        settings=SemanticSettings(),
    )
    schema_provider = BackendDatabaseSchemaProvider(client=client)

    assert not repo.is_ready()

    # Hot-path retrieve must reject cold start and NOT call client
    with pytest.raises(RuntimeError, match="SemanticLayerNotReady"):
        repo.retrieve("test question", top_k=5, allow_cold_start=False)

    # Hot-path load must reject cold start and NOT call client
    with pytest.raises(RuntimeError, match="SemanticLayerNotReady"):
        repo.load(allow_cold_start=False)

    # Hot-path schema must reject cold start and NOT call client
    with pytest.raises(RuntimeError, match="SchemaNotReady"):
        schema_provider.get_schema(allow_cold_start=False)

    # Zero Backend HTTP calls occurred!
    assert client.get_status.call_count == 0
    assert client.load_revision.call_count == 0
    assert client.download_index_artifact.call_count == 0


def test_atomic_swap_preserves_previous_revision_on_sync_failure():
    """Verify that when sync_active_index fails on a new revision, the old active revision remains intact."""
    client = MagicMock()
    zip_bytes_v1, _, _ = _create_sample_zip(revision_id="rev-v1", layer_id="sl-v1")

    # 1. Successfully load initial revision V1
    client.get_status.return_value = {"status": "Approved", "revisionId": "rev-v1"}
    client.load_revision.return_value = {
        "metadata": {"revision_id": "rev-v1", "semantic_layer_id": "sl-v1", "status": "approved"},
        "entities": [{"object_id": "e1", "name": "Entity1", "mapping": "tbl1"}],
        "relationships": [], "measures": [], "dimensions": [], "business_rules": [], "security_domains": [],
    }
    client.download_index_artifact.return_value = zip_bytes_v1

    embedding = MockEmbeddingService()
    repo = BackendSemanticRepository(
        client=client,
        embedding_service=embedding,
        settings=SemanticSettings(),
    )
    assert repo.sync_active_index() is True
    assert repo.indexed_revision_id == "rev-v1"
    assert repo.load()["metadata"]["revision_id"] == "rev-v1"
    initial_results = repo.retrieve("customers", 1)
    assert "rev-v1" in initial_results[0]["id"]

    # 2. Backend announces new revision V2, but download fails with 500 error
    client.get_status.return_value = {"status": "Approved", "revisionId": "rev-v2"}
    client.load_revision.return_value = {
        "metadata": {"revision_id": "rev-v2", "semantic_layer_id": "sl-v2", "status": "approved"},
        "entities": [{"object_id": "e2", "name": "Entity2", "mapping": "tbl2"}],
        "relationships": [], "measures": [], "dimensions": [], "business_rules": [], "security_domains": [],
    }
    client.download_index_artifact.side_effect = RuntimeError("HTTP 500 Internal Server Error")

    synced_v2 = repo.sync_active_index()
    assert synced_v2 is False

    # OLD REVISION V1 MUST REMAIN COMPLETELY INTACT AND HEALTHY
    assert repo.indexed_revision_id == "rev-v1"
    assert repo.load()["metadata"]["revision_id"] == "rev-v1"
    res_after_fail = repo.retrieve("customers", 1)
    assert "rev-v1" in res_after_fail[0]["id"]

    # 3. Now Backend provides corrupt ZIP for V2
    client.download_index_artifact.side_effect = None
    client.download_index_artifact.return_value = b"NOT_A_VALID_ZIP_FILE"
    synced_corrupt = repo.sync_active_index()
    assert synced_corrupt is False

    # Old revision V1 still remains intact!
    assert repo.indexed_revision_id == "rev-v1"
    assert repo.load()["metadata"]["revision_id"] == "rev-v1"
    res_after_corrupt = repo.retrieve("customers", 1)
    assert "rev-v1" in res_after_corrupt[0]["id"]


def test_real_http_transport_zero_calls_on_hot_path(monkeypatch):
    """Verify with REAL BackendHttpClient and requests calls that ZERO HTTP requests hit the network layer on hot path."""
    import requests
    from requests import Response
    from src.infrastructure.backend.backend_http_client import BackendHttpClient
    from src.infrastructure.backend.backend_semantic_client import BackendSemanticClient

    zip_bytes, _, _ = _create_sample_zip(revision_id="rev-real-http", layer_id="sl-real")

    # Custom HTTP handler to return real responses during warmup
    def warmup_http_get(url, *args, **kwargs):
        resp = Response()
        url_str = str(url)
        if "/status" in url_str:
            resp.status_code = 200
            resp._content = json.dumps({"status": "Approved", "revisionId": "rev-real-http"}).encode("utf-8")
        elif "/revisions/rev-real-http/index-artifact" in url_str:
            resp.status_code = 200
            resp._content = zip_bytes
        elif "/revisions/rev-real-http" in url_str:
            resp.status_code = 200
            resp._content = json.dumps({
                "semanticLayerId": "sl-real",
                "revisionId": "rev-real-http",
                "content": {
                    "metadata": {"revision_id": "rev-real-http", "semantic_layer_id": "sl-real", "status": "approved"},
                    "entities": [{"object_id": "e1", "name": "Customer", "mapping": "customers"}],
                    "relationships": [], "measures": [], "dimensions": [], "business_rules": [], "security_domains": [],
                }
            }).encode("utf-8")
        elif "/revisions/active/schema" in url_str:
            resp.status_code = 200
            resp._content = json.dumps({
                "revisionId": "rev-real-http",
                "schema": {"database": "PROD_DB", "tables": {"customers": {"columns": []}}},
            }).encode("utf-8")
        else:
            resp.status_code = 404
            resp._content = b"{}"
        return resp

    # Route requests during warmup to warmup_http_get
    monkeypatch.setattr(requests, "get", warmup_http_get)

    # Instantiate REAL Backend clients
    real_http = BackendHttpClient(base_url="http://test-backend.local", token="test-token")
    real_semantic_client = BackendSemanticClient(http_client=real_http)
    repo = BackendSemanticRepository(
        client=real_semantic_client,
        embedding_service=MockEmbeddingService(),
        settings=SemanticSettings(),
    )
    schema_provider = BackendDatabaseSchemaProvider(client=real_semantic_client)

    # 1. Warm-up phase uses the real HTTP client to initialize in memory
    assert repo.sync_active_index() is True
    assert schema_provider.sync_schema() is not None
    assert repo.is_ready()

    # 2. INSTALL FATAL HTTP TRAP on all network/HTTP methods:
    # ANY HTTP request or socket connection will immediately trigger AssertionError
    def fatal_http_trap(*args, **kwargs):
        raise AssertionError(f"FATAL: Real HTTP/network call attempted on hot path! Args: {args} {kwargs}")

    monkeypatch.setattr(requests, "get", fatal_http_trap)
    monkeypatch.setattr(requests, "post", fatal_http_trap)
    monkeypatch.setattr(requests, "put", fatal_http_trap)
    monkeypatch.setattr(requests, "request", fatal_http_trap)
    monkeypatch.setattr("http.client.HTTPConnection.connect", fatal_http_trap)

    # 3. Execute 5 consecutive user queries on the hot path
    questions = [
        "What are the top customer accounts?",
        "Total loan amount by branch?",
        "Active debit cards issued this month?",
        "Customers with delinquent balance?",
        "Transaction history for account 1001?",
    ]

    for q in questions:
        # Preflight schema check
        schema = schema_provider.get_schema()
        assert "tables" in schema

        # Semantic context retrieval
        layer = repo.load()
        assert layer["metadata"]["revision_id"] == "rev-real-http"

        results = repo.retrieve(q, top_k=3)
        assert len(results) > 0

        # Self-correction schema access
        schema2 = schema_provider.get_schema()
        assert schema2 is schema

    # SUCCESS: 5 questions passed with absolute ZERO HTTP/network calls!


