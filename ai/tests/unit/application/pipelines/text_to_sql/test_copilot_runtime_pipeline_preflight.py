"""Integration tests for PreflightService within CopilotRuntimePipeline."""

import json
from unittest.mock import Mock

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.dto.self_correction.self_correction_outcome import (
    SelfCorrectionOutcome,
)
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import (
    CopilotRuntimePipeline,
)
from src.application.services.preflight.enums import PreflightAction
from src.application.services.preflight.preflight_service import PreflightService


class SpyTextToSQLPipeline:
    def __init__(self, sql: str = "SELECT customer_id FROM customers;") -> None:
        self.sql = sql
        self.context_calls = 0
        self.run_calls = 0

    def build_context(self, question: str) -> str:
        self.context_calls += 1
        return "approved semantic context"

    def run(self, *args, **kwargs) -> GenerationResponse:
        self.run_calls += 1
        payload = json.dumps(
            {"status": "success", "sql": self.sql, "is_read_only": True}
        )
        return GenerationResponse(text=payload)


class SpySelfCorrection:
    def __init__(self) -> None:
        self.run_calls = 0

    def run(self, question, sql, semantic_context, **kwargs) -> SelfCorrectionOutcome:
        self.run_calls += 1
        return SelfCorrectionOutcome.success(sql, 0)


class MockSchemaProvider:
    def __init__(self, tables: list[str] | None = None) -> None:
        self.tables = tables or ["customers", "accounts", "branches"]

    def get_schema(self) -> dict:
        return {"tables": {t: {} for t in self.tables}}


def test_pipeline_without_preflight_service_preserves_existing_behavior() -> None:
    text_to_sql = SpyTextToSQLPipeline()
    self_corr = SpySelfCorrection()
    pipeline = CopilotRuntimePipeline(
        text_to_sql_pipeline=text_to_sql,
        self_correction_service=self_corr,
        preflight_service=None,
    )

    response = pipeline.run(
        CopilotAskRequest(question="Show customers", conversation=())
    )

    assert response.status == "Success"
    assert response.sql == "SELECT customer_id FROM customers;"
    assert text_to_sql.context_calls == 1
    assert text_to_sql.run_calls == 1
    assert self_corr.run_calls == 1


def test_pipeline_continues_when_preflight_skips() -> None:
    preflight = PreflightService(schema_provider=MockSchemaProvider())

    text_to_sql = SpyTextToSQLPipeline()
    self_corr = SpySelfCorrection()
    pipeline = CopilotRuntimePipeline(
        text_to_sql_pipeline=text_to_sql,
        self_correction_service=self_corr,
        preflight_service=preflight,
    )

    # General question with no explicit table reference -> SKIP -> pipeline proceeds normally
    response = pipeline.run(
        CopilotAskRequest(question="Show all customers and balances", conversation=())
    )

    assert response.status == "Success"
    assert text_to_sql.context_calls == 1
    assert text_to_sql.run_calls == 1
    assert self_corr.run_calls == 1


def test_pipeline_continues_when_preflight_passes() -> None:
    preflight = PreflightService(schema_provider=MockSchemaProvider())

    text_to_sql = SpyTextToSQLPipeline()
    self_corr = SpySelfCorrection()
    pipeline = CopilotRuntimePipeline(
        text_to_sql_pipeline=text_to_sql,
        self_correction_service=self_corr,
        preflight_service=preflight,
    )

    # Question with explicitly referenced existing table -> PASS -> pipeline proceeds normally
    response = pipeline.run(
        CopilotAskRequest(
            question="Show all records from table customers", conversation=()
        )
    )

    assert response.status == "Success"
    assert text_to_sql.context_calls == 1
    assert text_to_sql.run_calls == 1
    assert self_corr.run_calls == 1


def test_pipeline_blocks_and_bypasses_expensive_stages() -> None:
    preflight = PreflightService(schema_provider=MockSchemaProvider())

    text_to_sql = SpyTextToSQLPipeline()
    self_corr = SpySelfCorrection()
    pipeline = CopilotRuntimePipeline(
        text_to_sql_pipeline=text_to_sql,
        self_correction_service=self_corr,
        preflight_service=preflight,
    )

    # Question with explicitly referenced non-existent table -> BLOCK
    response = pipeline.run(
        CopilotAskRequest(
            question="Show accounts from table non_existent_table", conversation=()
        )
    )

    assert response.status == "Failed"
    assert response.error_code == "TABLE_NOT_FOUND"
    assert response.sql is None
    assert "non_existent_table" in (response.failure_reason or "")
    # Crucial: verify downstream expensive stages were completely bypassed!
    assert text_to_sql.context_calls == 0
    assert text_to_sql.run_calls == 0
    assert self_corr.run_calls == 0


def test_pipeline_records_preflight_observability_tags() -> None:
    preflight = PreflightService(schema_provider=MockSchemaProvider())

    observer = Mock()
    stage_mock = Mock()
    stage_mock.__enter__ = Mock(return_value={})
    stage_mock.__exit__ = Mock(return_value=None)
    observer.stage.return_value = stage_mock

    text_to_sql = SpyTextToSQLPipeline()
    self_corr = SpySelfCorrection()
    pipeline = CopilotRuntimePipeline(
        text_to_sql_pipeline=text_to_sql,
        self_correction_service=self_corr,
        observer=observer,
        preflight_service=preflight,
    )

    pipeline.run(
        CopilotAskRequest(
            question="Show data from table missing_table", conversation=()
        )
    )

    # Observer recorded preflight stage
    observer.stage.assert_any_call("preflight")
    # Observer recorded preflight tags on finish
    call_kwargs = observer.log.call_args.kwargs
    assert call_kwargs["tags"]["preflight_action"] == PreflightAction.BLOCK.value
    assert call_kwargs["tags"]["preflight_code"] == "TABLE_NOT_FOUND"


def test_pipeline_fails_open_when_schema_provider_errors() -> None:
    failing_provider = Mock()
    failing_provider.get_schema.side_effect = RuntimeError("Provider down")

    preflight = PreflightService(schema_provider=failing_provider)
    text_to_sql = SpyTextToSQLPipeline()
    self_corr = SpySelfCorrection()
    pipeline = CopilotRuntimePipeline(
        text_to_sql_pipeline=text_to_sql,
        self_correction_service=self_corr,
        preflight_service=preflight,
    )

    response = pipeline.run(
        CopilotAskRequest(
            question="Show accounts from table customers", conversation=()
        )
    )

    # Must fail open (SKIP) so normal generation proceeds
    assert response.status == "Success"
    assert text_to_sql.context_calls == 1
    assert text_to_sql.run_calls == 1
    assert self_corr.run_calls == 1
