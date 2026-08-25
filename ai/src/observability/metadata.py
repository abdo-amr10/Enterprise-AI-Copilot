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
    index = getattr(repository, "_vector_index", None)
    index_metadata = getattr(index, "_metadata", {}) if index else {}
    return {
        "semantic_revision": getattr(repository, "_cached_revision_id", None) or "unavailable",
        "embedding_provider": getattr(embedding, "backend", "unavailable"),
        "embedding_model": getattr(embedding, "model_name", "unavailable"),
        "embedding_version": getattr(embedding, "_model_version", None) or "unavailable",
        "embedding_dimension": getattr(embedding, "_embedding_dimension", None) or "unavailable",
        "index_type": getattr(index, "index_type", "unavailable"),
        "index_version": index_metadata.get("index_version", "unavailable"),
        "index_identity": index_metadata.get("revision_id", "unavailable"),
    }
