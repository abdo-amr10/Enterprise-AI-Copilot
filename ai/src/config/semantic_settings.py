"""Runtime configuration for semantic retrieval and indexing.

Configuration is intentionally kept outside application business logic.
"""
from dataclasses import dataclass
from pathlib import Path


AI_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SemanticSettings:
    default_top_k: int = 8
    embedding_model_path: Path = AI_ROOT / "models" / "embeddings" / "all-MiniLM-L6-v2"
    vector_index_filename: str = "semantic_index.npz"
    index_version: int = 1
