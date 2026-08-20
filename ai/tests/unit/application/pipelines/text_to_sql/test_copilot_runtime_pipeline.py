import json

from src.application.services.text_to_sql.reference_data_preflight import ReferenceDataPreflight

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


def test_runtime_pipeline_explains_missing_manager_value(tmp_path) -> None:
    data_path = tmp_path / "sample_data.json"
    data_path.write_text(
        json.dumps({"branches": [{"manager_name": "Sara Mahmoud"}]}),
        encoding="utf-8",
    )
    response = CopilotRuntimePipeline(
        FakeTextToSQLPipeline("this must not be generated"),
        reference_data_preflight=ReferenceDataPreflight(data_path),
    ).run(CopilotAskRequest(question="show accounts whose manager is Sergio Parker", conversation=()))

    assert response.status == "Failed"
    assert response.error_code == "REFERENCE_VALUE_NOT_FOUND"
    assert "Sergio Parker" in response.failure_reason
    assert response.suggestions == ("Show all accounts in branches managed by Sara Mahmoud.",)
