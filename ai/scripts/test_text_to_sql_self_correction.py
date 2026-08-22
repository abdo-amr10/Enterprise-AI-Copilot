"""Run the actual local AI Text-to-SQL generation and correction pipeline.

This script stops with validated SQL. It never executes SQL or contacts a
Backend database. It requires the configured approved semantic artifact,
FAISS index, BGE-M3 model, and Ollama models to be provisioned locally.
"""

from __future__ import annotations

import argparse
import json

from src.api.dependencies import get_context_service, get_self_correction_service
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import CopilotRuntimePipeline
from src.application.services.text_to_sql.sql_generation_service import SQLGenerationService
from src.application.services.text_to_sql.text_to_sql_pipeline import TextToSQLPipeline
from src.infrastructure.llm.model_config import QWEN_CONFIG
from src.infrastructure.llm.ollama_client import OllamaClient


def main(question: str) -> int:
    text_to_sql = TextToSQLPipeline(
        context_retrieval_service=get_context_service(),
        sql_generation_service=SQLGenerationService(OllamaClient(QWEN_CONFIG)),
    )
    print("=" * 50)
    print("TEXT-TO-SQL SELF-CORRECTION TEST")
    print("=" * 50)
    print(f"QUESTION:\n{question}\n")
    try:
        context = text_to_sql.build_context(question)
    except (FileNotFoundError, OSError, RuntimeError) as error:
        print("FINAL STATUS: FAILED (required local dependency is unavailable)")
        print("TECHNICAL DETAIL:", error)
        print(
            "FINAL HUMAN-READABLE RESPONSE:",
            "I’m sorry, but I couldn’t complete that request right now. Please try again.",
        )
        return 1
    print(f"SEMANTIC CONTEXT:\n{context}\n")
    generated = text_to_sql.run(question, semantic_context=context)
    payload = CopilotRuntimePipeline._parse_generation_response(generated.text)
    initial_sql = payload.get("sql")
    print(f"INITIAL SQL:\n{initial_sql}\n")
    if payload.get("status") != "success" or not isinstance(initial_sql, str):
        print("FINAL STATUS: FAILED (generation did not return a successful SQL contract)")
        return 1
    outcome = get_self_correction_service().run(question, initial_sql, context)
    for step in outcome.trace:
        print(f"ATTEMPT {step['attempt']}:")
        print("INITIAL/REVALIDATED SQL:", step["sql"])
        print("DETERMINISTIC ISSUES:", json.dumps(step["deterministicIssues"]))
        if "criticStatus" in step:
            print("CRITIC:", step["criticStatus"])
            print("VERIFIED CRITIC ISSUES:", json.dumps(step["verifiedCriticIssues"]))
        if "correctedSql" in step:
            print("CORRECTED SQL:", step["correctedSql"])
        print()
    print("FINAL SQL:", outcome.sql)
    print("FINAL STATUS:", "SUCCESS" if outcome.is_valid else "FAILED")
    print("ATTEMPTS USED:", outcome.attempts_used)
    print(
        "FINAL HUMAN-READABLE RESPONSE:",
        ("Your request was validated and is ready for Backend processing."
         if outcome.is_valid
         else "I’m sorry, but I couldn’t complete that request right now. Please try again."),
    )
    return 0 if outcome.is_valid else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True)
    raise SystemExit(main(parser.parse_args().question))
