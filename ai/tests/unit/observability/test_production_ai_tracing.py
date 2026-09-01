import time
from unittest.mock import Mock, MagicMock
import pytest

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.backend.copilot.text_to_sql_runtime_response import TextToSQLRuntimeResponse
from src.application.pipelines.text_to_sql.copilot_runtime_pipeline import CopilotRuntimePipeline
from src.observability.mlflow_observer import MLflowObserver
from src.observability.settings import ObservabilitySettings


class MockMLflowSink:
    def __init__(self):
        self.runs = []
        self.tags = {}
        self.metrics = {}
        self.ended_runs = 0
        self.artifacts_saved = []

    def set_tracking_uri(self, uri):
        pass

    def set_experiment(self, name):
        pass

    def start_run(self, tags=None, nested=True):
        self.runs.append(tags or {})
        self.tags.update(tags or {})
        return MagicMock(info=MagicMock(run_id=f"run-{len(self.runs)}"))

    def end_run(self):
        self.ended_runs += 1

    def log_metrics(self, metrics):
        self.metrics.update(metrics)

    def set_tags(self, tags):
        self.tags.update(tags)

    def log_dict(self, data, filename):
        self.artifacts_saved.append((filename, data))

    def log_text(self, text, filename):
        self.artifacts_saved.append((filename, text))


def test_runtime_pipeline_captures_correlation_metadata_and_ai_trace():
    sink = MockMLflowSink()
    settings = ObservabilitySettings(enabled=True)
    observer = MLflowObserver(settings=settings, mlflow_module=sink)

    t2sql = Mock()
    t2sql.build_context.return_value = "context"
    t2sql.run.return_value = Mock(text='{"status": "success", "sql": "SELECT 1", "is_read_only": true}')

    corr = Mock()
    corr.run.return_value = Mock(is_valid=True, sql="SELECT 1", attempts_used=0)

    pipeline = CopilotRuntimePipeline(
        text_to_sql_pipeline=t2sql,
        self_correction_service=corr,
        observer=observer,
    )

    request = CopilotAskRequest(
        question="Show something",
        correlation_id="corr-xyz-123",
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    )

    response = pipeline.run(request)
    assert response.status == "Success"
    assert sink.ended_runs == 1
    assert "ai_trace_id" in sink.tags
    assert sink.tags.get("correlation_id") == "corr-xyz-123"
    assert sink.tags.get("traceparent") == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    assert sink.tags.get("runtime_status") == "SUCCESS"


def test_runtime_pipeline_failsafe_when_mlflow_crashes():
    failing_sink = Mock()
    failing_sink.start_run.side_effect = RuntimeError("Tracking server unreachable")
    settings = ObservabilitySettings(enabled=True)
    observer = MLflowObserver(settings=settings, mlflow_module=failing_sink)

    t2sql = Mock()
    t2sql.build_context.return_value = "context"
    t2sql.run.return_value = Mock(text='{"status": "success", "sql": "SELECT 1", "is_read_only": true}')

    corr = Mock()
    corr.run.return_value = Mock(is_valid=True, sql="SELECT 1", attempts_used=0)

    pipeline = CopilotRuntimePipeline(
        text_to_sql_pipeline=t2sql,
        self_correction_service=corr,
        observer=observer,
    )

    request = CopilotAskRequest(question="Show something")
    # Pipeline must succeed without throwing exception despite MLflow failure
    response = pipeline.run(request)
    assert response.status == "Success"
    assert response.sql == "SELECT 1"


def test_raw_artifacts_never_saved_when_flag_is_false():
    sink = MockMLflowSink()
    # Explicitly default save_raw_artifacts=False
    settings = ObservabilitySettings(enabled=True, save_raw_artifacts=False)
    observer = MLflowObserver(settings=settings, mlflow_module=sink)
    observer.start({"test": "1"})

    observer.log_artifact_dict({"raw_query": "SELECT sensitive FROM vault"}, "query.json")
    observer.log_artifact_text("SELECT sensitive FROM vault", "query.sql")
    observer.finish()

    assert sink.artifacts_saved == []
