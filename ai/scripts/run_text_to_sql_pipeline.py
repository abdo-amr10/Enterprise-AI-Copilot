"""Run the Text-to-SQL pipeline interactively."""

from pathlib import Path
from src.infrastructure.llm.model_config import QWEN_CONFIG

from src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)
from src.application.services.text_to_sql.sql_generation_service import (
    SQLGenerationService,
)
from src.application.services.text_to_sql.text_to_sql_pipeline import (
    TextToSQLPipeline,
)

from src.infrastructure.llm.ollama_client import OllamaClient
from src.infrastructure.semantic_layer.retrieval.embedding_service import (
    EmbeddingService,
)
from src.infrastructure.semantic_layer.retrieval.vector_store import (
    LocalVectorStore,
)
from src.infrastructure.semantic_layer.retrieval.file_semantic_repository import (
    FileSemanticRepository,
)


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[1]

SEMANTIC_LAYER_PATH = (
    BASE_DIR / "outputs" / "semantic_layer" / "approved_semantic_layer.json"
)

SEMANTIC_INDEX_PATH = (
    BASE_DIR / "outputs" / "semantic_layer" / "semantic_index.npz"
)


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

TOP_K = 8


def build_pipeline() -> TextToSQLPipeline:
    """Build the Text-to-SQL pipeline and its dependencies."""

    embedding_service =EmbeddingService(
    model_path="models/embeddings/all-MiniLM-L6-v2"
)
    vector_store = LocalVectorStore(
        SEMANTIC_INDEX_PATH
    )

    semantic_repository = FileSemanticRepository(
        semantic_layer_path=SEMANTIC_LAYER_PATH,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )

    context_retrieval_service = ContextRetrievalService(
        semantic_repository=semantic_repository,
        default_top_k=TOP_K,
    )

    llm_client = OllamaClient(
    config=QWEN_CONFIG,
)

    sql_generation_service = SQLGenerationService(
        llm_client=llm_client,
    )

    return TextToSQLPipeline(
        context_retrieval_service=context_retrieval_service,
        sql_generation_service=sql_generation_service,
    )


def main() -> None:
    """Run the interactive Text-to-SQL pipeline."""

    print("=== Text-to-SQL Pipeline ===")
    print("Type 'exit' to stop.")
    print()

    pipeline = build_pipeline()

    while True:
        question = input("Question: ").strip()

        if question.lower() in {"exit", "quit"}:
            print("Pipeline stopped.")
            break

        if not question:
            print("Please enter a question.")
            continue

        print("\nGenerating SQL...\n")

        try:
            response = pipeline.run(
                question=question,
                top_k=TOP_K,
            )

            print("=== LLM Response ===")
            print(response.text)
            print()

        except Exception as exc:
            print("Pipeline error:")
            print(exc)
            print()


if __name__ == "__main__":
    main()