"""Best-effort, explicit and lazy MLflow recorder (no autologging)."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from src.observability.sanitization import safe_event
from src.observability.settings import ObservabilitySettings

logger = logging.getLogger(__name__)


def calculate_llm_cost(
    model_name: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    provider: str = "ollama",
) -> dict[str, float]:
    """Calculate input, output, and total costs in USD based on model pricing."""
    in_tok = max(0, int(input_tokens or 0))
    out_tok = max(0, int(output_tokens or 0))
    m = (model_name or "").lower()

    # Cost per 1M tokens in USD
    if "gpt-4o-mini" in m:
        input_rate, output_rate = 0.15, 0.60
    elif "gpt-4o" in m:
        input_rate, output_rate = 2.50, 10.00
    elif "claude-3-5-sonnet" in m or "claude-3.5-sonnet" in m:
        input_rate, output_rate = 3.00, 15.00
    elif "qwen" in m or provider == "ollama":
        # Standard local/open-weight inference cost benchmark
        input_rate, output_rate = 0.15, 0.20
    else:
        input_rate, output_rate = 0.15, 0.20

    in_cost = (in_tok / 1_000_000.0) * input_rate
    out_cost = (out_tok / 1_000_000.0) * output_rate
    tot_cost = in_cost + out_cost

    return {
        "input_cost": round(in_cost, 8),
        "output_cost": round(out_cost, 8),
        "total_cost": round(tot_cost, 8),
    }


class MLflowObserver:
    """Best-effort, explicit and lazy MLflow telemetry and tracing recorder.

    Records allowlisted, sanitized metadata, metrics, and spans without autologging.
    Spans wrap actual operation durations. All telemetry operations are fail-safe:
    if MLflow is disabled or the tracking server is unreachable, operations log a
    warning and continue gracefully without raising exceptions or impacting the AI runtime.
    """

    def __init__(
        self,
        settings: ObservabilitySettings | None = None,
        *,
        mlflow_module: Any | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        """Initialize the MLflow observer.

        Args:
            settings: Observability settings. If None, default settings are loaded.
            mlflow_module: Optional injected MLflow module for testing/mocking.
            clock: High-resolution monotonic clock function for latency timing.
        """
        self.settings = settings or ObservabilitySettings()
        self._provided_mlflow, self._clock = mlflow_module, clock
        self._mlflow: Any | None = None
        self._active = False
        self._run_id: str | None = None

    def start(self, tags: dict[str, Any]) -> None:
        """Start a new MLflow run if observability is enabled.

        Args:
            tags: Initial run metadata tags to attach. All tags are automatically
                sanitized to hash or redact sensitive values.
        """
        if not self.settings.enabled:
            return
        try:
            if self._provided_mlflow is None:
                import mlflow
                self._mlflow = mlflow
            else:
                self._mlflow = self._provided_mlflow
            if self.settings.tracking_uri:
                self._mlflow.set_tracking_uri(self.settings.tracking_uri)
            self._mlflow.set_experiment(self.settings.experiment_name)
            try:
                run = self._mlflow.start_run(
                    tags={k: str(v) for k, v in safe_event(tags).items() if v is not None},
                    nested=True,
                )
            except TypeError:
                run = self._mlflow.start_run(
                    tags={k: str(v) for k, v in safe_event(tags).items() if v is not None}
                )
            self._run_id = getattr(getattr(run, "info", None), "run_id", None)
            self._active = True
        except Exception as exc:
            logger.warning("MLflow observability unavailable: %s", type(exc).__name__)
            self._active = False

    @contextmanager
    def stage(self, name: str, **attributes: Any) -> Iterator[dict[str, float]]:
        """Context manager to measure and record the execution duration of a stage.

        Args:
            name: Identifier for the stage (e.g. 'retrieval', 'prompt', 'generation').
            **attributes: Additional sanitized attributes to attach to the span.

        Yields:
            A dictionary populated with `duration_ms` upon context exit.
        """
        started, span = self._clock(), None
        if self._active and self._mlflow is not None:
            try:
                start_span = getattr(self._mlflow, "start_span", None)
                if callable(start_span):
                    span = start_span(name=name)
            except Exception as exc:
                logger.warning("MLflow stage start failed: %s", type(exc).__name__)
        measurement: dict[str, float] = {}
        try:
            yield measurement
        finally:
            duration_ms = (self._clock() - started) * 1000
            measurement["duration_ms"] = duration_ms
            safe = safe_event({"stage": name, **attributes})
            if span is not None:
                try:
                    setter, end = getattr(span, "set_attributes", None), getattr(span, "end", None)
                    if callable(setter):
                        setter({**safe, "duration_ms": duration_ms})
                    if callable(end):
                        end()
                except Exception as exc:
                    logger.warning("MLflow stage span failed: %s", type(exc).__name__)
            self.log(metrics={f"stage.{name}.latency_ms": duration_ms}, tags={f"stage.{name}.{key}": value for key, value in safe.items()})

    def log(self, *, metrics: dict[str, float] | None = None, tags: dict[str, Any] | None = None) -> None:
        """Log numeric metrics and string tags to the active MLflow run.

        Args:
            metrics: Optional mapping of metric names to numeric values.
            tags: Optional mapping of tag names to values (sanitized before logging).
        """
        if not self._active or self._mlflow is None:
            return
        try:
            if metrics:
                self._mlflow.log_metrics({k: float(v) for k, v in metrics.items() if v is not None})
            if tags:
                self._mlflow.set_tags({k: str(v) for k, v in safe_event(tags).items() if v is not None})
        except Exception as exc:
            logger.warning("MLflow logging failed: %s", type(exc).__name__)

    def log_params(self, params: dict[str, Any]) -> None:
        """Log configuration parameters to the active MLflow run.

        Args:
            params: Mapping of parameter keys and values (sanitized before logging).
        """
        if not self._active or self._mlflow is None:
            return
        try:
            clean = {k: str(v) for k, v in safe_event(params).items() if v is not None}
            if clean:
                self._mlflow.log_params(clean)
        except Exception as exc:
            logger.warning("MLflow log_params failed: %s", type(exc).__name__)

    def log_artifact_dict(self, data: dict[str, Any], artifact_file: str) -> None:
        """Log a JSON-serializable dictionary as an artifact file.

        Args:
            data: Data dictionary to serialize and store.
            artifact_file: Relative filename for the saved artifact (e.g. 'debug_result.json').
        """
        if not self._active or self._mlflow is None or not self.settings.save_raw_artifacts:
            return
        try:
            log_dict = getattr(self._mlflow, "log_dict", None)
            if callable(log_dict):
                log_dict(data, artifact_file)
        except Exception as exc:
            logger.warning("MLflow log_dict failed: %s", type(exc).__name__)

    def log_artifact_text(self, text: str, artifact_file: str) -> None:
        """Log plain text content as an artifact file.

        Args:
            text: Text content to save.
            artifact_file: Relative filename for the saved artifact (e.g. 'generated_sql.sql').
        """
        if not self._active or self._mlflow is None or not self.settings.save_raw_artifacts:
            return
        try:
            log_text = getattr(self._mlflow, "log_text", None)
            if callable(log_text):
                log_text(text, artifact_file)
        except Exception as exc:
            logger.warning("MLflow log_text failed: %s", type(exc).__name__)

    def log_span(
        self,
        name: str,
        *,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        span_type: str | None = None,
    ) -> None:
        """Create a standalone OpenTelemetry / MLflow Span for diagnostic tracing.

        Args:
            name: Span operation name.
            inputs: Optional input payload dictionary (sanitized before logging).
            outputs: Optional output payload dictionary (sanitized before logging).
            attributes: Optional extra attributes (sanitized before logging).
            span_type: Optional span type (e.g. 'LLM', 'CHAIN', 'TOOL').
        """
        if not self._active or self._mlflow is None:
            return
        try:
            start_span = getattr(self._mlflow, "start_span", None)
            if callable(start_span):
                kwargs: dict[str, Any] = {"name": name}
                if span_type:
                    try:
                        from mlflow.entities import SpanType
                        kwargs["span_type"] = getattr(SpanType, span_type.upper(), span_type)
                    except Exception:
                        kwargs["span_type"] = span_type
                with start_span(**kwargs) as span:
                    if inputs and hasattr(span, "set_inputs"):
                        span.set_inputs(safe_event(inputs))
                    if attributes and hasattr(span, "set_attributes"):
                        span.set_attributes(safe_event(attributes))
                    if outputs and hasattr(span, "set_outputs"):
                        span.set_outputs(safe_event(outputs))
        except Exception as exc:
            logger.warning("MLflow span creation failed: %s", type(exc).__name__)

    def log_llm_span(
        self,
        name: str,
        *,
        prompt: str,
        response_text: str,
        model_name: str = "qwen2.5-coder:7b",
        provider: str = "ollama",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Log a dedicated LLM Span with real token counts and cost for MLflow 3 GenAI Tracing.

        Args:
            name: Span name (e.g. 'llm_sql_generation', 'sql_critic', 'sql_correction').
            prompt: Text prompt sent to the LLM.
            response_text: Text response returned by the LLM.
            model_name: Model identifier (e.g. 'qwen2.5-coder:7b').
            provider: Provider name (e.g. 'ollama').
            input_tokens: Real input/prompt token count.
            output_tokens: Real output/completion token count.
            attributes: Optional additional attributes to attach.
        """
        in_tok = int(input_tokens or (max(1, len(prompt.split()) * 4 // 3)))
        out_tok = int(output_tokens or (max(1, len(response_text.split()) * 4 // 3)))
        tot_tok = in_tok + out_tok

        cost_dict = calculate_llm_cost(model_name, in_tok, out_tok, provider)

        span_attrs: dict[str, Any] = {
            "mlflow.spanType": "LLM",
            "mlflow.llm.model": model_name,
            "mlflow.llm.provider": provider,
            "mlflow.chat.tokenUsage": {
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "total_tokens": tot_tok,
            },
            "mlflow.llm.cost": cost_dict,
        }
        if attributes:
            span_attrs.update(attributes)

        self.log_span(
            name=name,
            inputs={"prompt": prompt[:1000] if len(prompt) > 1000 else prompt},
            outputs={"response": response_text[:1000] if len(response_text) > 1000 else response_text},
            attributes=span_attrs,
            span_type="LLM",
        )

        self.log(
            metrics={
                "input_tokens": float(in_tok),
                "output_tokens": float(out_tok),
                "total_tokens": float(tot_tok),
                "total_cost": float(cost_dict["total_cost"]),
            },
            tags={
                "model_name": model_name,
                "model_provider": provider,
            }
        )

    def finish(self) -> None:
        """Finalize and close the active MLflow run."""
        if self._active and self._mlflow is not None:
            try:
                self._mlflow.end_run()
            except Exception as exc:
                logger.warning("MLflow finalization failed: %s", type(exc).__name__)
        self._active = False
        self._run_id = None

