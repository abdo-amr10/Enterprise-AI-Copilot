"""Installed command-line entry point for the local Text-to-SQL runtime."""

from __future__ import annotations

import argparse
import logging


def run_question(question: str, *, debug: bool = False) -> int:
    from src.api.dependencies import get_copilot_pipeline
    from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest

    result = get_copilot_pipeline().run(CopilotAskRequest(question=question, conversation=()))
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
    parser = argparse.ArgumentParser(description="Run the local Text-to-SQL pipeline.")
    parser.add_argument("--question")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print self-correction attempts, validation issues, and corrected SQL.",
    )
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
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
