"""Developer-only observer over existing production AI services."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from src.api.dependencies import get_copilot_pipeline, get_context_service, get_semantic_repository
from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.observability.metadata import model_metadata, prompt_metadata, retrieval_metadata
from src.observability.local_diagnostics import backend_request_diagnostic
from src.observability.mlflow_observer import MLflowObserver
from src.observability.sanitization import safe_error, stable_hash
from src.observability.settings import ObservabilitySettings
from src.observability.trace_policy import trace_reason

LAYERS = ("retrieval", "prompt", "generation", "validation", "critic", "correction", "full")
UNSUPPORTED_LAYERS = {"validation", "critic", "correction"}


@dataclass
class DebugResult:
    requested_layer: str
    prerequisites: tuple[str, ...]
    status: str
    metrics: dict[str, float] = field(default_factory=dict)
    tags: dict[str, Any] = field(default_factory=dict)
    local: dict[str, Any] = field(default_factory=dict)
    stopping_point: str = ""


class DebugRunner:
    """Uses production factories; only full invokes production orchestration."""
    def __init__(self, observer: MLflowObserver | None = None, *, run_type: str = "debug", repository_factory: Callable[[], Any] = get_semantic_repository, context_factory: Callable[[], Any] = get_context_service, pipeline_factory: Callable[[], Any] = get_copilot_pipeline, clock: Callable[[], float] = time.perf_counter) -> None:
        self._settings = ObservabilitySettings()
        self._observer = observer or MLflowObserver(self._settings, clock=clock)
        self._run_type, self._repository_factory, self._context_factory = run_type, repository_factory, context_factory
        self._pipeline_factory, self._clock = pipeline_factory, clock

    def run(self, question: str, layer: str = "full") -> DebugResult:
        if layer not in LAYERS: raise ValueError(f"Unknown layer '{layer}'. Choose one of: {', '.join(LAYERS)}.")
        repository, context_service = self._repository_factory(), self._context_factory()
        top_k = getattr(context_service, "_default_top_k", None)
        tags = {"run_type": self._run_type, "debug_layer": layer, "question_hash": stable_hash(question), "top_k": top_k if isinstance(top_k, int) else "unavailable", "input_tokens": "unavailable", "output_tokens": "unavailable", "total_tokens": "unavailable", **prompt_metadata(), **retrieval_metadata(repository)}
        prerequisites = {"retrieval": (), "prompt": ("retrieval",), "generation": ("retrieval", "prompt"), "full": ("request",)}
        result = DebugResult(layer, prerequisites.get(layer, ()), "passed", tags=tags)
        result.local["flow"] = self._initial_flow(layer)
        self._observer.start(tags)
        started = self._clock()
        try:
            if layer in UNSUPPORTED_LAYERS:
                result.status, result.stopping_point = "unsupported", "not independently callable with current production contract"
                result.tags["unsupported_reason"] = result.stopping_point
                return result
            indexed_before = getattr(repository, "_indexed_revision_id", None)
            if layer == "retrieval":
                with self._observer.stage("retrieval") as measure: documents = context_service.retrieve(question)
                result.metrics.update(retrieval_latency_ms=measure["duration_ms"], retrieval_result_count=float(len(documents)))
                result.local["retrieval"] = documents; result.stopping_point = "retrieval"
                result.local["flow"]["retrieval"].update(executed=True, status=result.status, duration_ms=result.metrics["retrieval_latency_ms"], result_count=len(documents))
            elif layer in {"prompt", "generation"}:
                pipeline = self._pipeline_factory()._text_to_sql_pipeline
                with self._observer.stage("retrieval") as measure: semantic_context = pipeline.build_context(question)
                result.metrics["retrieval_latency_ms"] = measure["duration_ms"]
                result.local["flow"]["retrieval"].update(executed=True, status="passed", duration_ms=measure["duration_ms"])
                with self._observer.stage("prompt") as measure: request = pipeline._prompt_service.build_request(question, semantic_context, date.today().isoformat())
                result.metrics.update(prompt_latency_ms=measure["duration_ms"], prompt_length=float(len(request.prompt)))
                result.local["flow"]["prompt"].update(executed=True, status="passed", duration_ms=measure["duration_ms"])
                result.local.update(semantic_context=semantic_context, prompt=request.prompt)
                if layer == "prompt": result.stopping_point = "prompt"
                else:
                    generation_service = pipeline._sql_generation_service
                    config = getattr(getattr(generation_service, "_llm_client", None), "_config", None)
                    if config: result.tags.update(model_metadata(config))
                    with self._observer.stage("generation") as measure: generation = generation_service.generate(request)
                    result.metrics["generation_latency_ms"] = measure["duration_ms"]
                    result.local["flow"]["generation"].update(executed=True, status="passed", duration_ms=measure["duration_ms"])
                    result.local["generation"] = generation.text; result.stopping_point = "generation"
            else:
                pipeline, events = self._pipeline_factory(), []
                generation_service = pipeline._text_to_sql_pipeline._sql_generation_service
                config = getattr(getattr(generation_service, "_llm_client", None), "_config", None)
                if config: result.tags.update(model_metadata(config))
                with self._observer.stage("request") as measure:
                    response = pipeline.run(CopilotAskRequest(question=question, conversation=()), trace_observer=events.append)
                result.metrics.update(request_latency_ms=measure["duration_ms"], validation_passed=float(response.status == "Success"))
                result.local["flow"]["request"].update(executed=True, status=response.status, duration_ms=measure["duration_ms"])
                for stage in ("retrieval", "prompt", "generation", "validation", "critic", "correction"):
                    result.local["flow"][stage].update(executed="unavailable", status="unavailable", reason="not exposed independently by production runtime full-flow contract")
                result.local.update(production_trace_events=events, final_sql=response.sql)
                result.stopping_point = "production validated-SQL boundary"
                if response.status != "Success": result.status = "failed"
            indexed_after = getattr(repository, "_indexed_revision_id", None)
            result.tags.update({"index_created": indexed_before is None and indexed_after is not None, "index_reused": indexed_before == indexed_after and indexed_after is not None, "index_rebuilt": indexed_before is not None and indexed_after is not None and indexed_before != indexed_after})
            return result
        except Exception as exc:
            result.status, result.tags["error_type"], result.local["local_error"] = "failed", safe_error(exc), str(exc)
            if layer in {"retrieval", "prompt", "generation"}:
                result.local["local_diagnostic"] = backend_request_diagnostic(exc)
            return result
        finally:
            result.metrics["total_latency_ms"] = (self._clock() - started) * 1000
            result.tags.update(retrieval_metadata(repository))
            result.tags["trace_reason"] = trace_reason({**result.metrics, "status": result.status}, self._settings, developer_debug=True)
            self._observer.log(metrics=result.metrics, tags=result.tags)
            self._observer.finish()

    @staticmethod
    def _initial_flow(layer: str) -> dict[str, dict[str, Any]]:
        return {stage: {"executed": False, "status": "not_executed", "duration_ms": "unavailable", "reason": "not requested"} for stage in ("request", "retrieval", "prompt", "generation", "validation", "critic", "correction", "final")}
