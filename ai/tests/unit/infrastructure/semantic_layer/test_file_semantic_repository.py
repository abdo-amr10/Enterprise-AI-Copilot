import json
import numpy as np
from pathlib import Path
import pytest

from src.infrastructure.semantic_layer.retrieval.file_semantic_repository import (
    FileSemanticRepository,
)


class _Embedding:
    model_name = "test-model"
    model_version = "test-version"
    embedding_dimension = 2

    def encode_documents(self, texts):
        return np.array([[1.0, 0.0] for _ in texts], dtype=np.float32)

    def encode_query(self, question):
        return np.array([1.0, 0.0], dtype=np.float32)


class _VectorStore:
    def __init__(self, initial_valid=False):
        self.is_valid = initial_valid
        self.build_calls = 0
        self.documents = []
        self.saved = False

    def validate_metadata(self, expected):
        if not self.is_valid:
            raise FileNotFoundError("FAISS index artifact is missing.")

    def build(self, documents, embeddings, metadata):
        self.build_calls += 1
        self.documents = list(documents)
        self.is_valid = True

    def save(self):
        self.saved = True

    def search(self, query, top_k):
        return [{**self.documents[0], "score": 0.99}]


def test_file_semantic_repository_auto_builds_when_index_missing(tmp_path: Path):
    layer_path = tmp_path / "approved_layer.json"
    layer_data = {
        "metadata": {
            "semantic_layer_id": "SL-1",
            "revision_id": "REV-1",
            "status": "approved",
        },
        "entities": [
            {
                "object_id": "customer",
                "name": "Customer",
                "description": "Customer records",
                "mapping": "customers",
            }
        ],
        "relationships": [],
        "measures": [],
        "dimensions": [],
        "business_rules": [],
    }
    layer_path.write_text(json.dumps(layer_data), encoding="utf-8")

    vector_store = _VectorStore(initial_valid=False)
    repo = FileSemanticRepository(
        semantic_layer_path=layer_path,
        embedding_service=_Embedding(),
        vector_store=vector_store,
    )

    # First retrieval: index was missing -> auto built
    results = repo.retrieve("show customers", top_k=1)
    assert len(results) == 1
    assert results[0]["object_id"] == "customer"
    assert results[0]["id"] == "SL-1:REV-1:entity:customer"
    assert vector_store.build_calls == 1
    assert vector_store.saved is True

    # Second retrieval: index is now valid -> no additional build call
    second_results = repo.retrieve("show customers", top_k=1)
    assert len(second_results) == 1
    assert vector_store.build_calls == 1
