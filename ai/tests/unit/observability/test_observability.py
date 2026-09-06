import builtins
import json
from types import SimpleNamespace

from src.observability.debug_runner import DebugRunner
from src.observability.mlflow_observer import MLflowObserver
from src.observability.sanitization import safe_event, stable_hash
from src.observability.settings import ObservabilitySettings


class FakeSpan:
    def __init__(self): self.attributes, self.ended = {}, False
    def set_attributes(self, values): self.attributes.update(values)
    def end(self): self.ended = True


class FakeMlflow:
    def __init__(self): self.calls, self.metrics, self.tags, self.spans = [], {}, {}, []
    def set_tracking_uri(self, value): self.calls.append(("uri", value))
    def set_experiment(self, value): self.calls.append(("experiment", value))
    def start_run(self, tags): self.calls.append(("start", tags))
    def end_run(self): self.calls.append(("end", None))
    def log_metrics(self, values): self.metrics.update(values)
    def set_tags(self, values): self.tags.update(values)
    def start_span(self, name):
        span = FakeSpan(); self.spans.append((name, span)); return span


class Clock:
    def __init__(self, *values): self.values = iter(values)
    def __call__(self): return next(self.values)


def test_disabled_observer_never_imports_or_uses_mlflow(monkeypatch) -> None:
    original_import = builtins.__import__
    def blocked_import(name, *args, **kwargs):
        if name == "mlflow": raise AssertionError("MLflow import attempted")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", blocked_import)
    sink = FakeMlflow()
    observer = MLflowObserver(ObservabilitySettings(enabled=False), mlflow_module=None)
    observer.start({"question": "private"})
    with observer.stage("request"): pass
    observer.finish()
    assert sink.calls == [] and sink.metrics == {}


def test_sensitive_values_are_never_raw_in_safe_events() -> None:
    event = {"question": "q", "prompt": "p", "sql": "SELECT 1", "semantic_context": "s", "raw_response": "r", "credentials": "secret", "exception": "details"}
    safe = safe_event(event)
    assert all(value not in safe.values() for value in event.values())
    assert safe["question_hash"] == stable_hash("q") and safe["sql_hash"] == stable_hash("SELECT 1")


def test_span_covers_actual_operation_duration_with_a_deterministic_clock() -> None:
    sink = FakeMlflow()
    observer = MLflowObserver(ObservabilitySettings(enabled=True), mlflow_module=sink, clock=Clock(1.0, 1.25))
    observer.start({"run_type": "test"})
    with observer.stage("retrieval") as measurement: pass
    assert measurement["duration_ms"] == 250.0
    assert sink.metrics["stage.retrieval.latency_ms"] == 250.0
    assert sink.spans[0][1].attributes["duration_ms"] == 250.0 and sink.spans[0][1].ended


class Repository:
    def __init__(self, revision=None):
        self._indexed_revision_id, self._cached_revision_id = revision, revision
        self._embedding_service = SimpleNamespace(backend="fake", model_name="embed", _model_version="1", _embedding_dimension=3)
        self._vector_index = SimpleNamespace(index_type="faiss", _metadata={"index_version": 1, "revision_id": revision or "new"})


class Context:
    _default_top_k = 7
    def __init__(self, repo, new_revision="new"): self.repo, self.new_revision = repo, new_revision
    def retrieve(self, question): self.repo._indexed_revision_id = self.new_revision; return []


def runner(repo, context, pipeline=lambda: None):
    return DebugRunner(repository_factory=lambda: repo, context_factory=lambda: context, pipeline_factory=pipeline)


def test_retrieval_lifecycle_and_actual_top_k_are_read_from_runtime_state() -> None:
    created_repo = Repository(); created = runner(created_repo, Context(created_repo)).run("q", "retrieval")
    reused_repo = Repository("new"); reused = runner(reused_repo, Context(reused_repo)).run("q", "retrieval")
    rebuilt_repo = Repository("old"); rebuilt = runner(rebuilt_repo, Context(rebuilt_repo)).run("q", "retrieval")
    assert created.tags["index_created"] and reused.tags["index_reused"] and rebuilt.tags["index_rebuilt"]
    assert created.tags["top_k"] == 7


def test_top_k_is_unavailable_only_when_the_runtime_exposes_no_value() -> None:
    repo = Repository()
    context = SimpleNamespace(retrieve=lambda question: [])
    assert runner(repo, context).run("q", "retrieval").tags["top_k"] == "unavailable"


def test_unsupported_layers_do_not_invoke_a_pipeline() -> None:
    repo, context = Repository(), Context(Repository())
    result = runner(repo, context, pipeline=lambda: (_ for _ in ()).throw(AssertionError("pipeline called"))).run("q", "critic")
    assert result.status == "unsupported"
    assert result.stopping_point == "not independently callable with current production contract"


def test_targeted_layers_stop_at_their_truthful_boundary() -> None:
    repo, context, calls = Repository(), Context(Repository()), []
    prompt_service = SimpleNamespace(build_request=lambda *args: calls.append("prompt") or SimpleNamespace(prompt="p"))
    generation_service = SimpleNamespace(
        _llm_client=SimpleNamespace(_config=None),
        generate=lambda request: calls.append("generation") or SimpleNamespace(text="{}"),
    )
    text_pipeline = SimpleNamespace(build_context=lambda question: calls.append("retrieval") or "context", _prompt_service=prompt_service, _sql_generation_service=generation_service)
    pipeline = SimpleNamespace(_text_to_sql_pipeline=text_pipeline)
    prompt = runner(repo, context, pipeline=lambda: pipeline).run("q", "prompt")
    assert calls == ["retrieval", "prompt"] and prompt.stopping_point == "prompt"
    calls.clear()
    generation = runner(repo, context, pipeline=lambda: pipeline).run("q", "generation")
    assert calls == ["retrieval", "prompt", "generation"] and generation.stopping_point == "generation"


def test_full_delegates_to_production_pipeline_without_executor_or_history_access() -> None:
    repo, context, called = Repository(), Context(Repository()), []
    production = SimpleNamespace(
        _text_to_sql_pipeline=SimpleNamespace(_sql_generation_service=SimpleNamespace(_llm_client=SimpleNamespace(_config=None))),
        run=lambda request, trace_observer: (called.append(request), SimpleNamespace(status="Success", sql="SELECT 1"))[1],
    )
    result = runner(repo, context, pipeline=lambda: production).run("q", "full")
    assert len(called) == 1 and result.stopping_point == "production validated-SQL boundary"
    assert not hasattr(production, "execute") and not hasattr(production, "history")


def test_self_correction_attempts_extracted_when_present() -> None:
    repo, context = Repository(), Context(Repository())
    def run_pipeline(request, trace_observer):
        trace_observer({"event": "initial_generation", "sql": "SELECT 1"})
        trace_observer({"action": "correction_required", "attempt": 0})
        trace_observer({"event": "after_correction", "attempt": 1})
        trace_observer({"event": "final_result", "attemptsUsed": 1, "status": "passed", "sql": "SELECT 1"})
        return SimpleNamespace(status="Success", sql="SELECT 1")

    production = SimpleNamespace(
        _text_to_sql_pipeline=SimpleNamespace(_sql_generation_service=SimpleNamespace(_llm_client=SimpleNamespace(_config=None))),
        run=run_pipeline,
    )
    result = runner(repo, context, pipeline=lambda: production).run("q", "full")
    assert result.metrics["self_correction_attempts_used"] == 1.0
    assert result.metrics["validation_passed"] == 1.0


def test_self_correction_attempts_not_fabricated_when_not_reached() -> None:
    repo, context = Repository(), Context(Repository())
    # Generation failure before self-correction
    def run_pipeline(request, trace_observer):
        return SimpleNamespace(status="Failed", sql=None, failure_reason="Generation failed")

    production = SimpleNamespace(
        _text_to_sql_pipeline=SimpleNamespace(_sql_generation_service=SimpleNamespace(_llm_client=SimpleNamespace(_config=None))),
        run=run_pipeline,
    )
    result = runner(repo, context, pipeline=lambda: production).run("q", "full")
    assert "self_correction_attempts_used" not in result.metrics
    assert result.metrics["validation_passed"] == 0.0


def test_validation_passed_metric_only_present_when_validation_reached() -> None:
    repo, context = Repository(), Context(Repository())
    # Retrieval layer does not run validation
    result_retrieval = runner(repo, context).run("q", "retrieval")
    assert "validation_passed" not in result_retrieval.metrics
    assert "self_correction_attempts_used" not in result_retrieval.metrics


def test_full_layer_needs_clarification_halts_before_validation() -> None:
    repo, context = Repository(), Context(Repository())
    validation_called = []
    
    prompt_service = SimpleNamespace(build_request=lambda *args: SimpleNamespace(prompt="Test prompt"))
    gen_text = json.dumps({
        "status": "needs_clarification",
        "sql": None,
        "warnings": ["Cannot create records automatically in read-only mode."]
    })
    generation_service = SimpleNamespace(
        _llm_client=SimpleNamespace(_config=None),
        generate=lambda req: SimpleNamespace(text=gen_text, input_tokens=10, output_tokens=10, total_tokens=20),
    )
    text_pipeline = SimpleNamespace(
        build_context=lambda q: "context",
        _prompt_service=prompt_service,
        _sql_generation_service=generation_service,
    )
    self_correction = SimpleNamespace(
        run=lambda **kwargs: validation_called.append(True) or SimpleNamespace(is_valid=False, issues=["Should not run"]),
    )
    production = SimpleNamespace(
        _text_to_sql_pipeline=text_pipeline,
        _self_correction_service=self_correction,
        _parse_generation_response=lambda text: json.loads(text),
        _FORBIDDEN_SQL=SimpleNamespace(search=lambda s: None),
    )

    result = runner(repo, context, pipeline=lambda: production).run(
        "Create a customer and report", "full"
    )

    assert result.status == "failed"
    assert result.tags["error_type"] == "NEEDS_CLARIFICATION"
    assert result.local["failure_reason"] == "Cannot create records automatically in read-only mode."
    assert result.local["flow"]["validation"]["executed"] is False
    assert len(validation_called) == 0
    assert result.metrics["validation_passed"] == 0.0


def test_full_layer_validation_failure_distinguished_from_pre_validation() -> None:
    repo, context = Repository(), Context(Repository())
    validation_called = []

    prompt_service = SimpleNamespace(build_request=lambda *args: SimpleNamespace(prompt="Test prompt"))
    gen_text = json.dumps({
        "status": "success",
        "sql": "SELECT customer_id FROM customers",
        "is_read_only": True,
        "warnings": []
    })
    generation_service = SimpleNamespace(
        _llm_client=SimpleNamespace(_config=None),
        generate=lambda req: SimpleNamespace(text=gen_text, input_tokens=10, output_tokens=10, total_tokens=20),
    )
    text_pipeline = SimpleNamespace(
        build_context=lambda q: "context",
        _prompt_service=prompt_service,
        _sql_generation_service=generation_service,
    )
    self_correction = SimpleNamespace(
        run=lambda **kwargs: validation_called.append(True) or SimpleNamespace(
            is_valid=False,
            sql="SELECT customer_id FROM customers",
            issues=["Column 'credit_rating' does not exist."],
            attempts_used=1,
            trace=[],
        ),
    )
    production = SimpleNamespace(
        _text_to_sql_pipeline=text_pipeline,
        _self_correction_service=self_correction,
        _parse_generation_response=lambda text: json.loads(text),
        _FORBIDDEN_SQL=SimpleNamespace(search=lambda s: None),
    )

    result = runner(repo, context, pipeline=lambda: production).run("Show customers", "full")

    assert result.status == "failed"
    assert result.tags["error_type"] == "VALIDATION_FAILED"
    assert "Validation failed: Column 'credit_rating' does not exist." in result.local["failure_reason"]
    assert result.local["flow"]["validation"]["executed"] is True
    assert len(validation_called) == 1


