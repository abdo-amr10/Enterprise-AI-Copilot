import numpy as np

from src.config.semantic_settings import SemanticSettings
from src.infrastructure.semantic_layer.retrieval.backend_semantic_repository import (
    BackendSemanticRepository,
)


class _Client:
    def __init__(self) -> None:
        self.revision_id = "REV-1"
        self.status_calls = 0
        self.revision_calls = 0

    def get_status(self):
        self.status_calls += 1
        return {"status": "Approved", "revisionId": self.revision_id}

    def load_revision(self, revision_id):
        self.revision_calls += 1
        return {
            "metadata": {"semantic_layer_id": "SL-1", "revision_id": revision_id, "status": "approved"},
            "entities": [
                {"object_id": "customer", "name": "Customer", "description": "Customer records", "mapping": "customers"},
                {"object_id": "loan", "name": "Loan", "description": "Loan accounts", "mapping": "loans"},
            ],
            "relationships": [], "measures": [], "dimensions": [], "business_rules": [],
        }


class _Embedding:
    model_name = "test-model"
    model_version = "test-version"
    embedding_dimension = 2

    def encode_documents(self, texts):
        assert len(texts) == 2
        return np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

    def encode_query(self, question):
        return np.array([1.0, 0.0], dtype=np.float32)


class _Index:
    def __init__(self):
        self.build_calls = 0
        self.documents = []

    def build(self, documents, embeddings, metadata):
        self.build_calls += 1
        self.documents = list(documents)

    def save(self):
        pass

    def search(self, query, top_k):
        return [{**self.documents[0], "score": 0.97}]


def test_backend_repository_uses_vector_index_and_rebuilds_only_for_new_revision():
    client, index = _Client(), _Index()
    repository = BackendSemanticRepository(
        client=client,
        embedding_service=_Embedding(),
        vector_index=index,
        settings=SemanticSettings(),
    )

    first = repository.retrieve("customers", 1)
    second = repository.retrieve("customers", 1)

    assert first[0]["type"] == "entity"
    assert first[0]["score"] == 0.97
    assert first[0]["revisionId"] == "REV-1"
    assert second[0]["id"] == first[0]["id"]
    assert index.build_calls == 1
    assert client.revision_calls == 1

    client.revision_id = "REV-2"
    repository.retrieve("customers", 1)

    assert index.build_calls == 2
    assert client.revision_calls == 2
