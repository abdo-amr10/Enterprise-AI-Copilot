import json

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import (
    CopilotRuntimePipeline,
)


class FakeTextToSQLPipeline:
    def __init__(self, text: str) -> None:
        self._text = text

    def run(self, question: str) -> GenerationResponse:
        return GenerationResponse(text=self._text)


def test_runtime_pipeline_returns_read_only_sql_to_backend() -> None:
    model_output = json.dumps(
        {"status": "success", "sql": "SELECT customer_id FROM customers;", "is_read_only": True}
    )
    response = CopilotRuntimePipeline(FakeTextToSQLPipeline(model_output)).run(
        CopilotAskRequest(question="Show customers", conversation=())
    )

    assert response.status == "Success"
    assert response.sql == "SELECT customer_id FROM customers;"


def test_runtime_pipeline_rejects_write_sql() -> None:
    model_output = json.dumps(
        {"status": "success", "sql": "DELETE FROM customers;", "is_read_only": True}
    )
    response = CopilotRuntimePipeline(FakeTextToSQLPipeline(model_output)).run(
        CopilotAskRequest(question="Delete customers", conversation=())
    )

    assert response.status == "Failed"
    assert response.error_code == "SQL_VALIDATION_FAILED"
