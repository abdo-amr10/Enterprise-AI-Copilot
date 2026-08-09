"""Runtime configuration for semantic retrieval and indexing.

Configuration is intentionally kept outside application business logic.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticSettings:
    default_top_k: int = 8
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    vector_index_filename: str = "semantic_index.npz"
