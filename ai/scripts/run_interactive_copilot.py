"""Interactive local Text-to-SQL diagnostics against a fresh test artifact.

The script never calls Semantic Layer generation and never executes SQL.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import CopilotRuntimePipeline
from src.application.services.context_retrieval.context_retrieval_service import ContextRetrievalService
from src.application.services.self_correction.critic_finding_verifier import CriticFindingVerifier
from src.application.services.self_correction.self_correction_service import SelfCorrectionService
from src.application.services.self_correction.sql_correction_service import SQLCorrectionService
from src.application.services.self_correction.sql_critic_service import SQLCriticService
from src.application.services.self_correction.validators.sql_relationship_validator import SQLRelationshipValidator
from src.application.services.self_correction.validators.sql_schema_validator import SQLSchemaValidator
from src.application.services.self_correction.validators.sql_syntax_validator import SQLSyntaxValidator
from src.application.services.text_to_sql.sql_generation_service import SQLGenerationService
from src.application.services.text_to_sql.text_to_sql_pipeline import TextToSQLPipeline
from src.config.self_correction_settings import SelfCorrectionSettings
from src.config.semantic_settings import SemanticSettings
from src.infrastructure.llm.model_config import QWEN_CONFIG, SQL_CORRECTION_CONFIG, SQL_CRITIC_CONFIG
from src.infrastructure.llm.ollama_client import OllamaClient
from src.infrastructure.semantic_layer.ingestion.database_schema_provider import DatabaseSchemaProvider
from src.infrastructure.semantic_layer.retrieval.embedding_service import EmbeddingService
from src.infrastructure.semantic_layer.retrieval.faiss_vector_index import FaissVectorIndex
from src.infrastructure.semantic_layer.retrieval.file_semantic_repository import FileSemanticRepository


OUTPUT_ROOT = PROJECT_ROOT / "tests" / "integration" / "live" / "outputs"
SEMANTIC_TEST_NAME = "test_real_semantic_layer_generation_validation_review_and_indexing"
SCHEMA_PATH = PROJECT_ROOT.parent / "docs" / "database_metadata" / "schema.json"


class CapturingLlmClient:
    """Record the genuine SQL-generation response without changing generation."""

    def __init__(self, delegate: OllamaClient) -> None:
        self._delegate = delegate
        self.last_response: GenerationResponse | None = None

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.last_response = self._delegate.generate(request)
        return self.last_response


class CapturingSelfCorrectionService:
    """Expose the genuine correction outcome returned to CopilotRuntimePipeline."""

    def __init__(self, delegate: SelfCorrectionService) -> None:
        self._delegate = delegate
        self.last_outcome: Any | None = None

    def run(self, question: str, sql: str, semantic_context: str | None = None) -> Any:
        self.last_outcome = self._delegate.run(question, sql, semantic_context)
        return self.last_outcome


def _latest_artifact_directory() -> Path:
    root = OUTPUT_ROOT / SEMANTIC_TEST_NAME
    candidates = [
        path for path in root.iterdir()
        if path.is_dir()
        and (path / "approved_semantic_layer.json").is_file()
        and (path / "semantic_index.faiss").is_file()
        and (path / "semantic_index.faiss.metadata.json").is_file()
    ] if root.is_dir() else []
    if not candidates:
        raise FileNotFoundError(
            "No approved Semantic Layer artifact was found. Run the Semantic Layer live test first."
        )
    return max(candidates, key=lambda path: path.name)


def _artifact_directory(value: str | None) -> Path:
    directory = Path(value).expanduser().resolve() if value else _latest_artifact_directory()
    required = (
        directory / "approved_semantic_layer.json",
        directory / "semantic_index.faiss",
        directory / "semantic_index.faiss.metadata.json",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Selected semantic artifact directory is incomplete:\n" + "\n".join(missing))
    return directory


def _local_runtime(artifact_directory: Path) -> tuple[CopilotRuntimePipeline, ContextRetrievalService, CapturingLlmClient, CapturingSelfCorrectionService]:
    settings = SemanticSettings()
    embedding = EmbeddingService(
        settings.production_embedding_model_path,
        model_name=settings.production_embedding_model_name,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        normalize=settings.normalize_embeddings,
    )
    repository = FileSemanticRepository(
        artifact_directory / "approved_semantic_layer.json",
        embedding_service=embedding,
        vector_store=FaissVectorIndex(artifact_directory / "semantic_index.faiss"),
    )
    context = ContextRetrievalService(repository, default_top_k=settings.default_top_k)
    syntax = SQLSyntaxValidator()
    schema = DatabaseSchemaProvider(SCHEMA_PATH)
    schema_validator = SQLSchemaValidator(schema, syntax)
    relationship_validator = SQLRelationshipValidator(repository, syntax, schema_validator)
    correction = SelfCorrectionService(
        context_retrieval_service=context,
        syntax_validator=syntax,
        schema_validator=schema_validator,
        relationship_validator=relationship_validator,
        critic_service=SQLCriticService(OllamaClient(SQL_CRITIC_CONFIG)),
        finding_verifier=CriticFindingVerifier(schema),
        correction_service=SQLCorrectionService(OllamaClient(SQL_CORRECTION_CONFIG)),
        max_attempts=SelfCorrectionSettings().max_attempts,
    )
    captured_correction = CapturingSelfCorrectionService(correction)
    captured_generation = CapturingLlmClient(OllamaClient(QWEN_CONFIG))
    runtime = CopilotRuntimePipeline(
        TextToSQLPipeline(context, SQLGenerationService(captured_generation)),
        captured_correction,
    )
    return runtime, context, captured_generation, captured_correction


def _print_section(title: str, value: Any) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    if isinstance(value, (dict, list, tuple)):
        print(json.dumps(value, indent=2, ensure_ascii=False, default=str))
    else:
        print(value)


def _save_question_artifacts(question: str, retrieval: list[dict[str, Any]], raw_response: str | None, outcome: Any, final: Any) -> Path:
    run_dir = OUTPUT_ROOT / "interactive_copilot" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir.mkdir(parents=True, exist_ok=False)
    for filename, value in {
        "question.json": {"question": question},
        "retrieval.json": retrieval,
        "generated_response.json": {"raw": raw_response},
        "self_correction.json": asdict(outcome) if outcome is not None else None,
        "final_response.json": asdict(final),
    }.items():
        (run_dir / filename).write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return run_dir


def _ask(question: str, runtime: CopilotRuntimePipeline, context: ContextRetrievalService, generation: CapturingLlmClient, correction: CapturingSelfCorrectionService) -> None:
    retrieval = context.retrieve(question)
    compact_retrieval = [
        {
            "type": item.get("type"), "name": item.get("payload", {}).get("name"),
            "mapping": item.get("payload", {}).get("mapping"), "score": item.get("score"),
        }
        for item in retrieval
    ]
    _print_section("QUESTION", question)
    _print_section("SEMANTIC RETRIEVAL", {"retrieved_count": len(retrieval), "items": compact_retrieval})
    final = runtime.run(CopilotAskRequest(question=question, conversation=()))
    raw = generation.last_response.text if generation.last_response else None
    _print_section("LLM GENERATED RESPONSE", raw or "No generation response was produced.")
    parsed: Any
    try:
        parsed = CopilotRuntimePipeline._parse_generation_response(raw) if raw else None
    except (json.JSONDecodeError, ValueError) as error:
        parsed = {"parse_error": str(error)}
    _print_section("GENERATED SQL", parsed)
    outcome = correction.last_outcome
    _print_section("SELF-CORRECTION", asdict(outcome) if outcome is not None else "Not reached by the runtime.")
    _print_section("FINAL RESULT", {
        "status": final.status,
        "final_sql": final.sql,
        "valid": bool(outcome and outcome.is_valid),
        "issues": list(outcome.issues) if outcome is not None else [],
        "correction_attempts": outcome.attempts_used if outcome is not None else 0,
        "failure_reason": final.failure_reason,
        "sql_execution": "NOT EXECUTED",
    })
    print(f"Diagnostic artifacts: {_save_question_artifacts(question, retrieval, raw, outcome, final)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local interactive Text-to-SQL diagnostics against a live-test artifact.")
    parser.add_argument("--semantic-artifacts", help="Timestamped live-test artifact directory. Defaults to the newest complete artifact.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        artifact_directory = _artifact_directory(args.semantic_artifacts)
        runtime, context, generation, correction = _local_runtime(artifact_directory)
    except Exception as error:
        print(f"Unable to initialize interactive Copilot: {error}", file=sys.stderr)
        return 1
    print("=" * 60)
    print("AI COPILOT INTERACTIVE TEST")
    print("=" * 60)
    print(f"Semantic Layer: {artifact_directory / 'approved_semantic_layer.json'}")
    print(f"Semantic Index: {artifact_directory / 'semantic_index.faiss'}")
    print("Type a question. Type 'exit' or 'quit' to stop.")
    try:
        while True:
            try:
                question = input("\nQuestion> ").strip()
            except EOFError:
                break
            if question.casefold() in {"exit", "quit"}:
                break
            if not question:
                print("Please enter a non-empty question.")
                continue
            _ask(question, runtime, context, generation, correction)
    except KeyboardInterrupt:
        print("\nInteractive Copilot stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
