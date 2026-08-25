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
    """Records allowlisted data only; spans wrap, rather than follow, work."""
    def __init__(self, settings: ObservabilitySettings | None = None, *, mlflow_module: Any | None = None, clock: Callable[[], float] = time.perf_counter) -> None:
        self.settings = settings or ObservabilitySettings()
        self._provided_mlflow, self._clock = mlflow_module, clock
        self._mlflow: Any | None = None
        self._active = False

    def start(self, tags: dict[str, Any]) -> None:
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
        """Keep the native span open for the actual observed operation."""
        started, span = self._clock(), None
        if self._active and self._mlflow is not None:
            try:
                start_span = getattr(self._mlflow, "start_span", None)
                if callable(start_span): span = start_span(name=name)
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
                    if callable(setter): setter({**safe, "duration_ms": duration_ms})
                    if callable(end): end()
                except Exception as exc:
                    logger.warning("MLflow stage span failed: %s", type(exc).__name__)
            self.log(metrics={f"stage.{name}.latency_ms": duration_ms}, tags={f"stage.{name}.{key}": value for key, value in safe.items()})

    def log(self, *, metrics: dict[str, float] | None = None, tags: dict[str, Any] | None = None) -> None:
        if not self._active or self._mlflow is None:
            return
        try:
            if metrics: self._mlflow.log_metrics({k: float(v) for k, v in metrics.items() if v is not None})
            if tags: self._mlflow.set_tags({k: str(v) for k, v in safe_event(tags).items() if v is not None})
        except Exception as exc:
            logger.warning("MLflow logging failed: %s", type(exc).__name__)

    def finish(self) -> None:
        if self._active and self._mlflow is not None:
            try: self._mlflow.end_run()
            except Exception as exc: logger.warning("MLflow finalization failed: %s", type(exc).__name__)
        self._active = False
