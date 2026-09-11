"""Installed command-line entry point for the local Text-to-SQL runtime."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path


AI_ROOT = Path(__file__).resolve().parents[1]
LOCAL_SEMANTIC_OUTPUT = AI_ROOT / "outputs" / "semantic_layer"


def ensure_local_semantic_index() -> None:
    """Build the derived local FAISS index when a local run has none yet.

    The approved semantic layer is the source artifact.  The FAISS files are
    derived artifacts and are intentionally recreated locally when absent.
    """
    from src.api.dependencies import is_local_development_mode
    from src.config.semantic_settings import SemanticSettings

    if not is_local_development_mode():
        return

    index_path = LOCAL_SEMANTIC_OUTPUT / SemanticSettings().vector_index_filename
    metadata_path = index_path.with_suffix(index_path.suffix + ".metadata.json")
    if index_path.is_file() and metadata_path.is_file():
        return

    print("Local FAISS semantic index is missing; building it from the approved semantic layer.")
    try:
        from scripts.build_semantic_index import main as build_semantic_index
    except ModuleNotFoundError:
        # ``python scripts/run_text_to_sql_pipeline.py`` places the scripts
        # directory (rather than the project root) on ``sys.path``.
        from build_semantic_index import main as build_semantic_index

    build_semantic_index()


def promote_latest_approved_semantic_artifact() -> None:
    """Promote the newest fully approved live Semantic artifact for local use."""
    from scripts.use_latest_live_semantic_artifact import (
        find_latest_successful_artifact,
        promote,
    )

    promote(find_latest_successful_artifact(), dry_run=False)


def run_question(question: str, *, debug: bool = False) -> int:
    """Run one local read-only question and render a user-facing outcome."""
    from src.api.dependencies import get_copilot_pipeline
    from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest

    try:
        result = get_copilot_pipeline().run(
            CopilotAskRequest(question=question, conversation=())
        )
    except KeyboardInterrupt:
        print("Request cancelled while waiting for the local AI model.")
        return 130
    if result.status == "Success":
        print("Your request was validated and sent to Backend for processing.")
        if debug:
            print(f"Validated SQL: {result.sql}")
        return 0
    print(result.message or "I’m sorry, but I couldn’t complete that request right now. Please try again.")
    if debug and result.failure_reason:
        print(f"Failure reason: {result.failure_reason}")
    if debug and result.rewritten_question:
        print(f"Rewritten question: {result.rewritten_question}")
    if debug and result.suggestions:
        print("Suggestions: " + "; ".join(result.suggestions))
    return 1


def main() -> int:
    """Parse CLI arguments and run single-question or interactive mode."""
    parser = argparse.ArgumentParser(description="Run the local Text-to-SQL pipeline.")
    parser.add_argument("--question")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print self-correction attempts, validation issues, and corrected SQL.",
    )
    parser.add_argument(
        "--use-latest-approved-semantic",
        action="store_true",
        help=(
            "Before running locally, promote the newest complete approved live Semantic "
            "Layer artifact to outputs/semantic_layer."
        ),
    )
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.use_latest_approved_semantic:
        try:
            promote_latest_approved_semantic_artifact()
        except (FileNotFoundError, ValueError) as exc:
            print(f"Could not load the latest approved Semantic Layer artifact: {exc}")
            return 2
    try:
        ensure_local_semantic_index()
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"Could not build the local FAISS semantic index: {exc}")
        return 2
    if args.question:
        return run_question(args.question, debug=args.verbose)
    print("=== Text-to-SQL Pipeline ===")
    print("Type 'exit' to stop.")
    while True:
        value = input("Question: ").strip()
        if value.lower() in {"exit", "quit"}:
            return 0
        if value:
            run_question(value, debug=args.verbose)
