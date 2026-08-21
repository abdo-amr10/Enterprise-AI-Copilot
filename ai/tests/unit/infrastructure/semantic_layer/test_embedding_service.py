import sys
import types

import numpy as np

from src.infrastructure.semantic_layer.retrieval.embedding_service import EmbeddingService


def test_embedding_service_loads_once_batches_and_normalizes(monkeypatch):
    calls = []

    class FakeModel:
        def get_sentence_embedding_dimension(self): return 2
        def encode(self, texts, **kwargs):
            calls.append((list(texts), kwargs))
            return [[3.0, 4.0] for _ in texts]

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(
        SentenceTransformer=lambda *args, **kwargs: FakeModel()
    ))
    service = EmbeddingService("offline-model", model_name="test", batch_size=2)
    first = service.encode_documents(["one", "two"])
    second = service.encode_query("three")
    assert len(calls) == 2
    assert first.dtype == np.float32 and first.shape == (2, 2)
    assert np.allclose(np.linalg.norm(first, axis=1), 1.0)
    assert np.allclose(np.linalg.norm(second), 1.0)
    assert service.embedding_dimension == 2
    assert service.model_name == "test"


def test_embedding_service_returns_empty_matrix_with_known_dimension(monkeypatch):
    class FakeModel:
        def get_sentence_embedding_dimension(self): return 3
        def encode(self, *_args, **_kwargs): raise AssertionError("should not encode")
    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(
        SentenceTransformer=lambda *args, **kwargs: FakeModel()
    ))
    result = EmbeddingService("offline-model").encode_documents([])
    assert result.shape == (0, 3)
