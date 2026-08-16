"""Run the complete local Text-to-SQL pipeline without the .NET Backend."""

from __future__ import annotations

import argparse

def run_question(question: str) -> int:
    from src.api.dependencies import get_copilot_pipeline
    from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest

    result = get_copilot_pipeline().run(CopilotAskRequest(question=question))

    if result.status == "Success":
        print(result.sql)
        return 0

    print(f"{result.error_code}: {result.message}")
    return 1


def main(question: str | None = None) -> int:
    if question:
        return run_question(question)

    print("=== Text-to-SQL Pipeline ===")
    print("Type 'exit' to stop.")
    while True:
        value = input("Question: ").strip()
        if value.lower() in {"exit", "quit"}:
            return 0
        if value:
            run_question(value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--question")
    args = parser.parse_args()
    raise SystemExit(main(args.question))
