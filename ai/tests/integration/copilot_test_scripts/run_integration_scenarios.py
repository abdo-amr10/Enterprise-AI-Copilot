"""Print Backend-facing Copilot AI-runtime integration transcripts.

This does not start an HTTP server. It exercises the real application
pipelines and records their inputs and outputs in the same shape a Backend
controller would exchange with the AI runtime.

Usage:
    python -m tests.integration.copilot_test_scripts.run_integration_scenarios
"""

from __future__ import annotations

import json

from src.application.dto.backend.copilot.copilot_ask_request import (
    CopilotAskRequest,
)
from src.application.dto.backend.copilot.semantic_retrieval_request import (
    SemanticRetrievalRequest,
)
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.pipelines.context_retrieval.semantic_retrieval_pipeline import (
    SemanticRetrievalPipeline,
)
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import (
    CopilotRuntimePipeline,
)


class FakeRetrievalService:
    """Deterministic approved-semantic-layer retrieval for the transcript."""

    def retrieve(self, question: str, top_k: int | None = None):
        return [
            {
                "type": "relationship",
                "payload": {
                    "from_table": "Sales",
                    "to_table": "Customers",
                },
            },
            {
                "type": "business_rule",
                "payload": {"description": "Active customers have Status = 1."},
            },
        ]


class FakeTextToSQLPipeline:
    """Deterministic LLM output for success and SQL-safety failure cases."""

    def __init__(self, generated_text: str) -> None:
        self._generated_text = generated_text

    def build_context(self, question: str) -> str:
        return "approved semantic context"

    def run(
        self,
        question: str,
        semantic_context: str | None = None,
        correction_feedback: str = "",
    ) -> GenerationResponse:
        return GenerationResponse(text=self._generated_text)


class FakeSelfCorrectionService:
    def run(self, question: str, sql: str, semantic_context: str):
        from src.application.dto.self_correction.self_correction_outcome import SelfCorrectionOutcome
        return SelfCorrectionOutcome.success(sql, attempts_used=0)


class MockCopilotBackend:
    """Backend-owned orchestration needed to produce the public API contract."""

    def __init__(self, runtime_pipeline: CopilotRuntimePipeline, query_id: str) -> None:
        self._runtime_pipeline = runtime_pipeline
        self._query_id = query_id

    def ask(self, request: dict) -> dict:
        runtime_response = self._runtime_pipeline.run(
            CopilotAskRequest(
                question=request["question"],
                conversation=tuple(request["conversation"]),
            )
        )
        if runtime_response.status == "Failed":
            return {
                "queryId": self._query_id,
                "status": "Failed",
                "errorCode": runtime_response.error_code,
                "message": runtime_response.message,
            }

        # Represents Backend-side RLS, SQL execution, and report formatting.
        return {
            "queryId": self._query_id,
            "status": "Completed",
            "report": {
                "textSummary": (
                    "The total revenue for active customers this month is $145,000."
                ),
                "presentationType": "SummaryCard",
                "data": [{"TotalAmount": 145000.00}],
            },
        }


def _call(
    transcript: list[dict],
    step: str,
    method: str,
    path: str,
    request: dict,
    handler,
) -> dict:
    response = handler()
    transcript.append(
        {
            "step": step,
            "method": method,
            "path": path,
            "request": request,
            "response": response,
        }
    )
    return response


def build_transcript() -> list[dict]:
    """Run the retrieval and Text-to-SQL handoffs and return their transcript."""

    transcript: list[dict] = []
    question = "Show total revenue for active customers."
    conversation: list[dict] = []
    request_body = {"question": question, "conversation": conversation}

    retrieval_pipeline = SemanticRetrievalPipeline(FakeRetrievalService())
    _call(
        transcript,
        "3.4 Internal Semantic Retrieval",
        "POST",
        "/internal/semantic/retrieve",
        request_body,
        lambda: retrieval_pipeline.run(
            SemanticRetrievalRequest(question=question, conversation=tuple(conversation))
        ).to_dict(),
    )

    valid_model_output = json.dumps(
        {
            "status": "success",
            "sql": (
                "SELECT SUM(s.Amount) AS TotalRevenue "
                "FROM Sales AS s "
                "INNER JOIN Customers AS c ON c.CustomerId = s.CustomerId "
                "WHERE c.Status = 1;"
            ),
            "is_read_only": True,
        }
    )
    runtime_pipeline = CopilotRuntimePipeline(
        FakeTextToSQLPipeline(valid_model_output), FakeSelfCorrectionService()
    )
    backend = MockCopilotBackend(runtime_pipeline, query_id="req-990")
    _call(
        transcript,
        "3.1 Main Copilot Interface (success)",
        "POST",
        "/api/v1/copilot/ask",
        request_body,
        lambda: backend.ask(request_body),
    )

    unsafe_model_output = json.dumps(
        {
            "status": "success",
            "sql": "DELETE FROM Customers;",
            "is_read_only": True,
        }
    )
    unsafe_backend = MockCopilotBackend(
        CopilotRuntimePipeline(FakeTextToSQLPipeline(unsafe_model_output), FakeSelfCorrectionService()),
        query_id="req-991",
    )
    _call(
        transcript,
        "3.1 Main Copilot Interface (write SQL rejected)",
        "POST",
        "/api/v1/copilot/ask",
        {"question": "Delete all customers", "conversation": []},
        lambda: unsafe_backend.ask(
            {"question": "Delete all customers", "conversation": []}
        ),
    )

    return transcript


def main() -> None:
    print(json.dumps(build_transcript(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
