import numpy as np
import pytest
import inspect

from src.application.pipelines.semantic_layer.semantic_layer_embedding_pipeline import SemanticLayerEmbeddingPipeline
from src.infrastructure.semantic_layer.retrieval.semantic_document_builder import SemanticDocumentBuilder
from src.infrastructure.semantic_layer.retrieval.semantic_index_builder import SemanticIndexBuilder


class _EmbeddingService:
    model_name = "test-model"
    model_version = "test-version"
    embedding_dimension = 2

    def encode_documents(self, texts):
        assert texts
        return np.array([[1.0, 0.0] for _ in texts], dtype=np.float32)


class _Index:
    def __init__(self): self.calls = []
    def build(self, documents, embeddings, metadata): self.calls.append((documents, embeddings, metadata))
    def save(self): self.calls.append("saved")


def _layer(status="approved"):
    return {"metadata": {"semantic_layer_id": "SL-001", "revision_id": "REV-001", "status": status},
            "entities": [{"object_id": "obj-customer", "name": "Customer", "description": "A buyer."}],
            "relationships": [], "measures": [], "dimensions": [], "business_rules": []}


def test_document_builder_uses_object_identity_and_semantic_text():
    document = SemanticDocumentBuilder().build(_layer())[0]
    assert document["id"] == "SL-001:REV-001:entity:obj-customer"
    assert document["object_id"] == "obj-customer"
    assert "Entity" in document["text"] and "A buyer." in document["text"]
    assert "object_id" not in document["text"]


def test_document_builder_renders_all_semantic_object_types():
    layer = _layer()
    layer["relationships"] = [{"object_id": "obj-rel", "name": "Customer orders", "from_table": "customers", "to_table": "orders", "cardinality": "one_to_many"}]
    layer["measures"] = [{"object_id": "obj-measure", "name": "Revenue", "description": "Sales total", "aggregation": "sum"}]
    layer["dimensions"] = [{"object_id": "obj-dimension", "name": "Region", "description": "Sales region"}]
    layer["business_rules"] = [{"object_id": "obj-rule", "name": "Active customer", "description": "Status is active"}]
    documents = SemanticDocumentBuilder().build(layer)
    assert {document["object_type"] for document in documents} == {
        "entity", "relationship", "measure", "dimension", "business_rule"
    }
    assert any("cardinality: one_to_many" in document["text"] for document in documents)


def test_index_builder_processes_backend_provided_layer_in_memory():
    index = _Index()
    result = SemanticIndexBuilder(_EmbeddingService(), index).build(_layer())
    documents, vectors, metadata = index.calls[0]
    assert documents[0]["payload"]["name"] == "Customer"
    assert vectors.dtype == np.float32
    assert metadata["semantic_layer_id"] == "SL-001"
    assert metadata["embedding_model"] == "test-model"
    assert index.calls[-1] == "saved"
    assert result["document_count"] == 1


def test_embedding_pipeline_requires_backend_provided_approved_revision():
    pipeline = SemanticLayerEmbeddingPipeline(SemanticIndexBuilder(_EmbeddingService(), _Index()))
    with pytest.raises(ValueError, match="approved"):
        pipeline.run(_layer("validated"))


def test_production_embedding_path_has_no_local_semantic_layer_dependency():
    source = "\n".join((
        inspect.getsource(SemanticIndexBuilder),
        inspect.getsource(SemanticLayerEmbeddingPipeline),
    ))
    for forbidden in (
        "FileSemanticRepository", "LocalVectorStore", "database_metadata",
        "approved_semantic_layer.json", "outputs/semantic_layer",
    ):
        assert forbidden not in source
