import importlib.util

import numpy as np
import pytest

from src.infrastructure.semantic_layer.retrieval.faiss_vector_index import FaissVectorIndex


pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("faiss") is None,
    reason="faiss-cpu is an optional installed production dependency in this environment",
)


def test_faiss_index_searches_cosine_and_rejects_incompatible_metadata(tmp_path):
    index = FaissVectorIndex(tmp_path / "semantic.faiss")
    documents = [{"id": "one"}, {"id": "two"}]
    index.build(documents, np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32), {
        "index_version": 1, "semantic_layer_id": "SL", "revision_id": "REV",
        "embedding_model": "model", "embedding_model_version": "v1",
        "embedding_dimension": 2, "similarity_metric": "cosine",
        "index_type": "faiss.IndexFlatIP", "document_count": 2,
    })
    index.save()
    assert index.search(np.array([1.0, 0.0], dtype=np.float32), 1)[0]["id"] == "one"
    with pytest.raises(ValueError, match="top_k"):
        index.search(np.array([1.0, 0.0], dtype=np.float32), 0)
    with pytest.raises(ValueError, match="revision_id"):
        index.validate_metadata({"revision_id": "OTHER"})
