import json

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import (
    CopilotRuntimePipeline,
)


class FakeTextToSQLPipeline:
    def __init__(self, text: str) -> None:
        self._text = text

    def build_context(self, question: str) -> str:
        return "approved semantic context"

    def run(
        self,
        question: str,
        semantic_context: str | None = None,
        correction_feedback: str = "",
    ) -> GenerationResponse:
        return GenerationResponse(text=self._text)


class FakeSelfCorrection:
    def __init__(self, valid=True): self.valid = valid
    def run(self, question, sql, semantic_context, trace_observer=None):
        from src.application.dto.self_correction.self_correction_outcome import SelfCorrectionOutcome
        return SelfCorrectionOutcome.success(sql, 0) if self.valid else SelfCorrectionOutcome.failure(3, ("invalid",))


def test_runtime_pipeline_returns_read_only_sql_to_backend() -> None:
    model_output = json.dumps(
        {"status": "success", "sql": "SELECT customer_id FROM customers;", "is_read_only": True}
    )
    response = CopilotRuntimePipeline(FakeTextToSQLPipeline(model_output), FakeSelfCorrection()).run(
        CopilotAskRequest(question="Show customers", conversation=())
    )

    assert response.status == "Success"
    assert response.sql == "SELECT customer_id FROM customers;"


def test_runtime_pipeline_rejects_write_sql() -> None:
    model_output = json.dumps(
        {"status": "success", "sql": "DELETE FROM customers;", "is_read_only": True}
    )
    response = CopilotRuntimePipeline(FakeTextToSQLPipeline(model_output), FakeSelfCorrection()).run(
        CopilotAskRequest(question="Show customers", conversation=())
    )

    assert response.status == "Failed"
    assert response.error_code == "SQL_VALIDATION_FAILED"


def test_runtime_pipeline_rejects_write_intent_before_calling_the_model() -> None:
    response = CopilotRuntimePipeline(
        FakeTextToSQLPipeline("not used"), FakeSelfCorrection()
    ).run(CopilotAskRequest(question="Insert a new account", conversation=()))

    assert response.status == "Failed"
    assert response.error_code == "READ_ONLY_REQUEST_REQUIRED"
    assert "read-only" in response.message


def test_runtime_pipeline_maps_exhausted_corrections_to_a_stable_failure() -> None:
    model_output = json.dumps(
        {"status": "success", "sql": "SELECT customer_id FROM customers;", "is_read_only": True}
    )
    response = CopilotRuntimePipeline(
        FakeTextToSQLPipeline(model_output), FakeSelfCorrection(valid=False)
    ).run(CopilotAskRequest(question="Show customers", conversation=()))
    assert response.status == "Failed"
    assert response.error_code == "MAX_RETRIES_EXCEEDED"


def test_runtime_pipeline_emits_optional_trace_without_changing_response() -> None:
    model_output = json.dumps(
        {"status": "success", "sql": "SELECT customer_id FROM customers;", "is_read_only": True}
    )
    trace = []

    response = CopilotRuntimePipeline(
        FakeTextToSQLPipeline(model_output), FakeSelfCorrection()
    ).run(
        CopilotAskRequest(question="Show customers", conversation=()),
        trace_observer=trace.append,
    )

    assert response.status == "Success"
    assert trace == [
        {"event": "initial_generation", "sql": "SELECT customer_id FROM customers;"},
        {
            "event": "final_result",
            "sql": "SELECT customer_id FROM customers;",
            "attemptsUsed": 0,
            "status": "passed",
        },
    ]
