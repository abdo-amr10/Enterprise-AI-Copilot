"""Best-effort, explicit and lazy MLflow recorder (no autologging)."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from src.observability.sanitization import safe_event
from src.observability.settings import ObservabilitySettings

logger = logging.getLogger(__name__)


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
            self._mlflow.start_run(tags={k: str(v) for k, v in safe_event(tags).items() if v is not None})
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
        if not self._active or self._mlflow is None:
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
        if not self._active or self._mlflow is None:
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
    ) -> None:
        """Create a standalone OpenTelemetry / MLflow Span for diagnostic tracing.

        Args:
            name: Span operation name.
            inputs: Optional input payload dictionary (sanitized before logging).
            outputs: Optional output payload dictionary (sanitized before logging).
            attributes: Optional extra attributes (sanitized before logging).
        """
        if not self._active or self._mlflow is None:
            return
        try:
            start_span = getattr(self._mlflow, "start_span", None)
            if callable(start_span):
                with start_span(name=name) as span:
                    if inputs and hasattr(span, "set_inputs"):
                        span.set_inputs(safe_event(inputs))
                    if attributes and hasattr(span, "set_attributes"):
                        span.set_attributes(safe_event(attributes))
                    if outputs and hasattr(span, "set_outputs"):
                        span.set_outputs(safe_event(outputs))
        except Exception as exc:
            logger.warning("MLflow span creation failed: %s", type(exc).__name__)

    def finish(self) -> None:
        """Finalize and close the active MLflow run."""
        if self._active and self._mlflow is not None:
            try:
                self._mlflow.end_run()
            except Exception as exc:
                logger.warning("MLflow finalization failed: %s", type(exc).__name__)
        self._active = False

