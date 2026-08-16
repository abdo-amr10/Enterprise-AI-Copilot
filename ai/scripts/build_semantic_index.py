"""Build the semantic vector index from the approved semantic layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config.semantic_settings import SemanticSettings
from src.infrastructure.semantic_layer.retrieval.embedding_service import (
    EmbeddingService,
)
from src.infrastructure.semantic_layer.retrieval.semantic_index_builder import (
    SemanticIndexBuilder,
)
from src.infrastructure.semantic_layer.retrieval.vector_store import (
    LocalVectorStore,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "semantic_layer"

APPROVED_LAYER_PATH = (
    OUTPUT_DIR / "approved_semantic_layer.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    """Load and return a JSON object from the given file."""

    if not path.exists():
        raise FileNotFoundError(
            f"Approved semantic layer not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object in: {path}"
        )

    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write a dictionary to a JSON file."""

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    """Build embeddings and persist the semantic vector index."""

    # 1. Load approved semantic layer.
    approved_layer = _load_json(
        APPROVED_LAYER_PATH
    )

    # 2. Verify that the semantic layer is actually approved.
    metadata = approved_layer.get("metadata", {})

    if metadata.get("status") != "approved":
        raise ValueError(
            "The semantic layer must be human-approved "
            "before indexing."
        )

    # 3. Load semantic runtime settings.
    settings = SemanticSettings()

    index_path = OUTPUT_DIR / settings.vector_index_filename

    # 4. Initialize embedding service.
    embedding_service = EmbeddingService(
        settings.embedding_model_path
    )

    # 5. Initialize local vector store.
    vector_store = LocalVectorStore(index_path)

    # 6. Build and persist the vector index.
    index_builder = SemanticIndexBuilder(
        embedding_service,
        vector_store,
    )

    result = index_builder.build(
        approved_layer
    )

    # 7. Save indexing metadata.
    result["index_path"] = str(
        index_path.relative_to(PROJECT_ROOT)
    )

    _write_json(
        OUTPUT_DIR / "index_build_result.json",
        result,
    )

    print("\n=== Semantic Index Build ===")
    print(
        f"Documents: {result['document_count']}"
    )
    print(
        f"Embedding dimension: "
        f"{result['embedding_dimension']}"
    )
    print(
        f"Embedding backend: "
        f"{result['embedding_backend']}"
    )
    print(
        f"Index: {result['index_path']}"
    )

    print("\nSemantic index built successfully.")


if __name__ == "__main__":
    main()
