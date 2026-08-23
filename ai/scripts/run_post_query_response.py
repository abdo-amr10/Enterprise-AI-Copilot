"""Runner for PostQueryResponseFormatter against a real (or fixture) backend result.

Structured the same way as the installed ``enterprise-ai-copilot`` command:
a thin entry point that imports the real project code and calls it. No
formatting/response logic is duplicated here.

Usage:
    python run_post_query_response.py --question "..." --backend-result fixture.json
    python run_post_query_response.py --question "..." --backend-result fixture.json --with-summary

``--backend-result`` points to a JSON file shaped like:
    {
        "status": "Success",
        "columns": ["product_name", "total_sales"],
        "rows": [["Laptop", 12000], ["Phone", 8500]],
        "row_count": 2,
        "error_code": null,
        "error_message": null
    }

``row_count`` is optional — if you leave it out (or set it to null),
BackendExecutionResult.effective_row_count will compute it from ``rows``
instead. If ``status`` is "Failed", ``error_message`` is required (the
real DTO raises ValueError otherwise); ``error_code`` is optional in
either case.

This lets you try the formatter with a result you already got back from
Backend (paste it into the fixture file) without needing a live call.

``--with-summary`` wires in the real PostQueryResponseSummarizer, backed
by the real OllamaClient — this makes an actual local LLM call, so it
requires Ollama to be running with the configured model available.
Without this flag, the response ``text`` is the deterministic default
from PostQueryResponseFormatter (no LLM call at all).
"""

from __future__ import annotations

import argparse
import base64
import json
from dataclasses import asdict

from src.application.dto.backend.copilot.execution_result import BackendExecutionResult
from src.application.services.post_query_response.post_query_response_formatter import (
    PostQueryResponseFormatter,
)
from src.application.services.post_query_response.post_query_response_summarizer import (
    PostQueryResponseSummarizer,
)
from src.infrastructure.llm.model_config import QWEN_CONFIG
from src.infrastructure.llm.ollama_client import OllamaClient

# No dedicated summarization model config exists yet in model_config.py
# (only QWEN_CONFIG, SQL_CORRECTION_CONFIG, SQL_CRITIC_CONFIG were seen).
# QWEN_CONFIG is used here as the closest general-purpose fit. Swap this
# import for a dedicated config if/when one is added.
_SUMMARY_MODEL_CONFIG = QWEN_CONFIG


def load_backend_result(path: str) -> BackendExecutionResult:
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    return BackendExecutionResult(
        status=data["status"],
        columns=tuple(data.get("columns", [])),
        rows=tuple(tuple(row) for row in data.get("rows", [])),
        row_count=data.get("row_count"),
        error_code=data.get("error_code"),
        error_message=data.get("error_message"),
        metadata=data.get("metadata", {}),
    )


def save_excel_if_present(response, output_dir: str) -> None:
    """When the response carries an inline XLSX payload, write it to disk
    so it can actually be opened, instead of only showing base64 in the
    printed JSON."""
    if not response.file_content_base64:
        return
    import os

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, response.file_name)
    with open(output_path, "wb") as file:
        file.write(base64.b64decode(response.file_content_base64))
    print(f"\n[Excel file written to: {output_path}]")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a backend result through PostQueryResponseFormatter.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--backend-result", required=True, help="Path to a JSON fixture of the backend result.")
    parser.add_argument(
        "--excel-output-dir",
        default="scripts/output",
        help="Directory to save the generated .xlsx file into, when the response is an Excel presentation.",
    )
    parser.add_argument(
        "--with-summary",
        action="store_true",
        help="Call the real LLM summarizer (via Ollama) to generate the response text, instead of the "
             "deterministic default text.",
    )
    args = parser.parse_args()

    backend_result = load_backend_result(args.backend_result)

    summarizer = None
    if args.with_summary:
        # If Ollama isn't reachable, PostQueryResponseFormatter._with_summary
        # already falls back to the deterministic text on any exception —
        # a summarizer failure never turns a successful query into an error.
        summarizer = PostQueryResponseSummarizer(llm_client=OllamaClient(config=_SUMMARY_MODEL_CONFIG))

    formatter = PostQueryResponseFormatter(summarizer=summarizer)
    response = formatter.format(args.question, backend_result)

    # PostQueryResponse is expected to be a dataclass; asdict() gives a
    # plain dict we can dump straight to JSON. The base64 payload is left
    # in place here so you can see it's actually populated; the decoded
    # file itself is written separately below.
    print(json.dumps(asdict(response), ensure_ascii=False, indent=2))
    save_excel_if_present(response, args.excel_output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())