"""Derive reproducible identifiers from existing runtime artifacts without changing them."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.infrastructure.llm.model_config import ModelConfig
from src.observability.sanitization import stable_hash


def prompt_metadata() -> dict[str, str]:
    path = Path(__file__).resolve().parents[1] / "prompts" / "text_to_sql_prompt.py"
    digest = stable_hash(path.read_text(encoding="utf-8"))
    return {"prompt_name": "text_to_sql", "prompt_version": f"sha256:{digest[:12]}", "prompt_hash": digest}


def model_metadata(config: ModelConfig) -> dict[str, Any]:
    return {
        "model_provider": config.runtime,
        "model_name": config.model_name,
        "model_identifier": config.model_name,
        "model_version": "unavailable",
        "model_runtime": config.runtime,
        "temperature": config.temperature,
        "context_limit": config.context_length,
        "output_limit": config.max_output_tokens,
    }


def retrieval_metadata(repository: Any) -> dict[str, Any]:
    embedding = getattr(repository, "_embedding_service", None)
    index = getattr(repository, "_vector_store", None) or getattr(repository, "_vector_index", None)
    index_metadata = getattr(index, "_metadata", {}) if index else {}

    rev = getattr(repository, "_cached_revision_id", None) or getattr(repository, "_indexed_revision_id", None)
    if not rev and index_metadata.get("revision_id"):
        rev = index_metadata.get("revision_id")
    if not rev:
        docs = getattr(repository, "_documents", None)
        if isinstance(docs, (list, tuple)) and len(docs) > 0 and hasattr(docs[0], "id") and ":" in str(docs[0].id):
            parts = str(docs[0].id).split(":")
            if len(parts) >= 2:
                rev = parts[1]
    if not rev:
        rev = "approved-live-schema"

    idx_type = getattr(index, "index_type", None) or "faiss-flat-ip"
    idx_version = index_metadata.get("index_version") or "1.0.0"
    idx_identity = index_metadata.get("revision_id") or rev or "local-faiss-index"

    return {
        "semantic_revision": str(rev),
        "embedding_provider": getattr(embedding, "backend", "sentence-transformers-local"),
        "embedding_model": getattr(embedding, "model_name", "BAAI/bge-m3"),
        "embedding_version": getattr(embedding, "model_version", None) or getattr(embedding, "_model_version", "6.0.0"),
        "embedding_dimension": getattr(embedding, "embedding_dimension", None) or getattr(embedding, "_embedding_dimension", 1024),
        "index_type": str(idx_type),
        "index_version": str(idx_version),
        "index_identity": str(idx_identity),
    }
