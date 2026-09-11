"""Runtime configuration for semantic retrieval and indexing.

Configuration is intentionally kept outside application business logic.
"""
import os
from dataclasses import dataclass
from pathlib import Path


AI_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SemanticSettings:
    default_top_k: int = int(os.getenv("SEMANTIC_DEFAULT_TOP_K", "8"))
    # The selected offline production artifact is provisioned with the runtime.
    production_embedding_model_name: str = "BAAI/bge-m3"
    production_embedding_model_path: Path = AI_ROOT / "models" / "embeddings" / "bge-m3"
    embedding_device: str | None = None
    embedding_batch_size: int = 32
    normalize_embeddings: bool = True
    vector_index_filename: str = "semantic_index.faiss"
    index_version: int = 1
    index_type: str = "faiss.IndexFlatIP"
    similarity_metric: str = "cosine"
