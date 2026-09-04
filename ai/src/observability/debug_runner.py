"""Developer-only diagnostic execution runner over existing AI services.

Allows developers and evaluators to run isolated stages (retrieval, prompt, generation, full)
without modifying production code or coupling business logic to telemetry.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from src.api.dependencies import get_copilot_pipeline, get_context_service, get_semantic_repository
from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.observability.audit_context import RequestAuditContext
from src.observability.audit_summary import build_request_summary
from src.observability.latency_audit import stage as audit_stage, request_lifecycle
from src.observability.metadata import model_metadata, prompt_metadata, retrieval_metadata
from src.observability.local_diagnostics import backend_request_diagnostic
from src.observability.mlflow_observer import MLflowObserver
from src.observability.sanitization import safe_error, stable_hash
from src.observability.settings import ObservabilitySettings
from src.observability.trace_policy import trace_reason
from src.prompts.text_to_sql_prompt import TEXT_TO_SQL_PROMPT

LAYERS = ("retrieval", "prompt", "generation", "validation", "critic", "correction", "full")
UNSUPPORTED_LAYERS = {"validation", "critic", "correction"}


def _extract_tables(sql: str | None) -> list[str]:
    if not sql or not isinstance(sql, str):
        return []
    try:
        import sqlglot
        from sqlglot.expressions import Table
        parsed = sqlglot.parse_one(sql)
        tables = [t.name for t in parsed.find_all(Table) if t.name]
        if tables:
            return sorted(list(set(tables)))
    except Exception:
        pass
    import re
    matches = re.findall(r'\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)', sql, re.IGNORECASE)
    filtered = [m for m in matches if m.lower() not in {"select", "where", "group", "order", "having", "limit"}]
    return sorted(list(set(filtered)))


@dataclass
class DebugResult:
    """Outcome and captured metrics from an isolated debug execution.

    Attributes:
        requested_layer: The target layer requested (e.g. 'retrieval', 'generation', 'full').
        prerequisites: Dependent layers executed before the target layer.
        status: Execution status ('passed', 'failed', 'unsupported').
        metrics: Captured latency and quality metrics.
        tags: Sanitized metadata tags.
        local: Intermediate artifacts and diagnostics (for local developer inspection).
        stopping_point: Description of the stage where execution completed or halted.
    """

    requested_layer: str
    prerequisites: tuple[str, ...]
    status: str
    metrics: dict[str, float] = field(default_factory=dict)
    tags: dict[str, Any] = field(default_factory=dict)
    local: dict[str, Any] = field(default_factory=dict)
    stopping_point: str = ""


class DebugRunner:
    """Developer diagnostic harness for inspecting isolated AI pipeline layers.

    Uses existing production service factories without executing customer SQL
    or mutating persistent data. Emits sanitized MLflow traces and local artifacts.
    """

    def __init__(
        self,
        observer: MLflowObserver | None = None,
        *,
        run_type: str = "debug",
        repository_factory: Callable[[], Any] = get_semantic_repository,
        context_factory: Callable[[], Any] = get_context_service,
        pipeline_factory: Callable[[], Any] = get_copilot_pipeline,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        """Initialize the debug runner.

        Args:
            observer: Optional MLflow observer instance.
            run_type: Run classification tag ('debug', 'evaluation', etc.).
            repository_factory: Factory for resolving the semantic repository.
            context_factory: Factory for resolving the context retrieval service.
            pipeline_factory: Factory for resolving the copilot runtime pipeline.
            clock: Monotonic clock callable for latency timing.
        """
        self._settings = ObservabilitySettings()
        self._observer = observer or MLflowObserver(self._settings, clock=clock)
        self._run_type, self._repository_factory, self._context_factory = run_type, repository_factory, context_factory
        self._pipeline_factory, self._clock = pipeline_factory, clock

    def run(self, question: str, layer: str = "full") -> DebugResult:
        """Execute the requested AI layer for a question and capture diagnostics.

        Args:
            question: The natural language question to process.
            layer: The target execution layer ('full', 'retrieval', 'prompt', 'generation').

        Returns:
            A DebugResult containing captured metrics, tags, and local output.

        Raises:
            ValueError: If an unknown layer identifier is requested.
        """
        if layer not in LAYERS: raise ValueError(f"Unknown layer '{layer}'. Choose one of: {', '.join(LAYERS)}.")
        repository, context_service = self._repository_factory(), self._context_factory()
        top_k = getattr(context_service, "_default_top_k", None)
        tags = {"run_type": self._run_type, "debug_layer": layer, "question_hash": stable_hash(question), "top_k": top_k if isinstance(top_k, int) else "unavailable", "input_tokens": "unavailable", "output_tokens": "unavailable", "total_tokens": "unavailable", **prompt_metadata(), **retrieval_metadata(repository)}
        prerequisites = {"retrieval": (), "prompt": ("retrieval",), "generation": ("retrieval", "prompt"), "full": ("request",)}
        result = DebugResult(layer, prerequisites.get(layer, ()), "passed", tags=tags)
        result.local["flow"] = self._initial_flow(layer)
        self._observer.start(tags)
        started = self._clock()
        audit_ctx: RequestAuditContext | None = None
        lifecycle_cm = request_lifecycle(
            request_id=f"debug_{layer}_{stable_hash(question)[:8]}",
            correlation_id=f"debug_corr_{stable_hash(question)[:8]}",
        )
        try:
            audit_ctx = lifecycle_cm.__enter__()
        except Exception:
            pass

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
                with self._observer.stage("prompt") as measure:
                    with audit_stage("prompt_construction"):
                        request = pipeline._prompt_service.build_request(question, semantic_context, date.today().isoformat())
                result.metrics.update(prompt_latency_ms=measure["duration_ms"], prompt_length=float(len(request.prompt)))
                result.local["flow"]["prompt"].update(executed=True, status="passed", duration_ms=measure["duration_ms"])
                result.local.update(semantic_context=semantic_context, prompt=request.prompt)
                if layer == "prompt": result.stopping_point = "prompt"
                else:
                    generation_service = pipeline._sql_generation_service
                    config = getattr(getattr(generation_service, "_llm_client", None), "_config", None)
                    if config: result.tags.update(model_metadata(config))
                    with self._observer.stage("generation") as measure:
                        with audit_stage("sql_generation", is_leaf=False):
                            with audit_stage("llm_inference"):
                                generation = generation_service.generate(request)
                    result.metrics["generation_latency_ms"] = measure["duration_ms"]
                    result.local["flow"]["generation"].update(executed=True, status="passed", duration_ms=measure["duration_ms"])
                    
                    in_tok = getattr(generation, "input_tokens", None)
                    out_tok = getattr(generation, "output_tokens", None)
                    tot_tok = getattr(generation, "total_tokens", None)
                    if in_tok is not None:
                        result.tags["input_tokens"] = str(in_tok)
                        result.metrics["input_tokens"] = float(in_tok)
                    if out_tok is not None:
                        result.tags["output_tokens"] = str(out_tok)
                        result.metrics["output_tokens"] = float(out_tok)
                    if tot_tok is not None:
                        result.tags["total_tokens"] = str(tot_tok)
                        result.metrics["total_tokens"] = float(tot_tok)

                    clean_gen_sql = generation.text
                    try:
                        cleaned = generation.text.strip()
                        if cleaned.startswith("```") and cleaned.endswith("```"):
                            cleaned = "\n".join(cleaned.splitlines()[1:-1]).strip()
                        parsed = json.loads(cleaned)
                        if isinstance(parsed, dict) and "sql" in parsed:
                            clean_gen_sql = parsed["sql"]
                    except Exception:
                        pass
                    result.local["generation"] = clean_gen_sql
                    result.stopping_point = "generation"
                    tables_used = _extract_tables(clean_gen_sql)
                    result.tags["tables"] = ", ".join(tables_used) if tables_used else "none"
                    result.tags["tables_count"] = len(tables_used)
                    result.local["tables_used"] = tables_used
                    result.local["tables_count"] = len(tables_used)
                    
                    if hasattr(self._observer, "log_llm_span"):
                        self._observer.log_llm_span(
                            "llm_raw_sql_generation",
                            prompt=request.prompt,
                            response_text=clean_gen_sql,
                            model_name=getattr(generation, "model_name", None) or "qwen2.5-coder:7b",
                            provider=getattr(generation, "provider", None) or "ollama",
                            input_tokens=in_tok,
                            output_tokens=out_tok,
                        )
                    else:
                        self._observer.log_span("llm_raw_sql_generation", inputs={"prompt": request.prompt[:300]}, outputs={"raw_sql": clean_gen_sql})
            else:
                pipeline, events = self._pipeline_factory(), []
                text_to_sql = pipeline._text_to_sql_pipeline
                generation_service = text_to_sql._sql_generation_service
                config = getattr(getattr(generation_service, "_llm_client", None), "_config", None)
                if config: result.tags.update(model_metadata(config))

                # Execute granular production stages to measure real latency and populate stage breakdown
                can_run_granular = (
                    hasattr(text_to_sql, "build_context")
                    and hasattr(text_to_sql, "_prompt_service")
                    and hasattr(pipeline, "_self_correction_service")
                    and hasattr(pipeline._self_correction_service, "run")
                )

                if can_run_granular:
                    with audit_stage("pipeline", is_leaf=False):
                        # 1. Semantic Retrieval Stage
                        with self._observer.stage("retrieval") as measure_ret:
                            semantic_context = text_to_sql.build_context(question)
                        result.metrics["retrieval_latency_ms"] = measure_ret["duration_ms"]
                        result.local["flow"]["retrieval"].update(executed=True, status="passed", duration_ms=measure_ret["duration_ms"])
                        result.local["semantic_context"] = semantic_context

                        # 2. Prompt Construction Stage
                        with self._observer.stage("prompt") as measure_prompt:
                            with audit_stage("prompt_construction"):
                                prompt_req = text_to_sql._prompt_service.build_request(question, semantic_context, date.today().isoformat())
                        result.metrics.update(prompt_latency_ms=measure_prompt["duration_ms"], prompt_length=float(len(prompt_req.prompt)))
                        result.local["flow"]["prompt"].update(executed=True, status="passed", duration_ms=measure_prompt["duration_ms"])
                        result.local["prompt"] = prompt_req.prompt

                        # 3. LLM SQL Generation Stage
                        with self._observer.stage("generation") as measure_gen:
                            with audit_stage("sql_generation", is_leaf=False):
                                with audit_stage("llm_inference"):
                                    gen_response = generation_service.generate(prompt_req)
                        result.metrics["generation_latency_ms"] = measure_gen["duration_ms"]
                        result.local["flow"]["generation"].update(executed=True, status="passed", duration_ms=measure_gen["duration_ms"])

                    in_tok = getattr(gen_response, "input_tokens", None)
                    out_tok = getattr(gen_response, "output_tokens", None)
                    tot_tok = getattr(gen_response, "total_tokens", None)
                    if in_tok is not None:
                        result.tags["input_tokens"] = str(in_tok)
                        result.metrics["input_tokens"] = float(in_tok)
                    if out_tok is not None:
                        result.tags["output_tokens"] = str(out_tok)
                        result.metrics["output_tokens"] = float(out_tok)
                    if tot_tok is not None:
                        result.tags["total_tokens"] = str(tot_tok)
                        result.metrics["total_tokens"] = float(tot_tok)

                    try:
                        payload = pipeline._parse_generation_response(gen_response.text)
                    except Exception:
                        payload = {}
                    initial_sql = payload.get("sql", "").strip() if isinstance(payload, dict) else ""
                    events.append({
                        "event": "initial_generation",
                        "sql": initial_sql,
                        "prompt": prompt_req.prompt,
                        "raw_response": gen_response.text,
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "model_name": getattr(gen_response, "model_name", None) or "qwen2.5-coder:7b",
                        "provider": getattr(gen_response, "provider", None) or "ollama",
                    })

                    # 4. Validation & Self-Correction Stage
                    with self._observer.stage("validation") as measure_val:
                        outcome = pipeline._self_correction_service.run(
                            question=question,
                            sql=initial_sql,
                            semantic_context=semantic_context,
                            trace_observer=events.append,
                            enforce_rls=True,
                        )
                    result.metrics["validation_latency_ms"] = measure_val["duration_ms"]
                    val_status = "passed" if outcome.is_valid else "failed"

                    trace_events = getattr(outcome, "trace", ())
                    det_dur = sum(
                        float(step.get("deterministicDurationMs", 0.0))
                        for step in trace_events
                        if isinstance(step, dict) and "deterministicDurationMs" in step
                    )
                    critic_dur = sum(
                        float(step.get("criticDurationMs", 0.0))
                        for step in trace_events
                        if isinstance(step, dict) and "criticDurationMs" in step
                    )
                    corr_dur = sum(
                        float(step.get("correctionDurationMs", 0.0))
                        for step in trace_events
                        if isinstance(step, dict) and "correctionDurationMs" in step
                    )
                    critic_ran = any(
                        step.get("criticExecuted") or "criticStatus" in step
                        for step in trace_events
                        if isinstance(step, dict)
                    )

                    result.metrics["deterministic_validation_latency_ms"] = det_dur
                    if critic_ran:
                        result.metrics["critic_latency_ms"] = critic_dur
                    if corr_dur > 0:
                        result.metrics["correction_latency_ms"] = corr_dur

                    # 4. Deterministic Validation Stage
                    result.local["flow"]["validation"].update(
                        executed=True,
                        status="passed" if val_status == "passed" else "failed",
                        duration_ms=det_dur if det_dur > 0 else (measure_val["duration_ms"] if not critic_ran else 0.0),
                    )

                    # 5. LLM Critic Check Stage
                    attempts_used = getattr(outcome, "attempts_used", 0)
                    if critic_ran:
                        result.local["flow"]["critic"].update(
                            executed=True,
                            status="passed",
                            duration_ms=critic_dur,
                        )
                    else:
                        result.local["flow"]["critic"].update(
                            executed=False,
                            status="skipped (deterministic issues)",
                            duration_ms=0.0,
                        )

                    # 6. SQL Self-Correction Stage
                    if attempts_used > 0:
                        result.local["flow"]["correction"].update(
                            executed=True,
                            status=f"corrected ({attempts_used} attempts)",
                            duration_ms=corr_dur,
                        )
                    else:
                        result.local["flow"]["correction"].update(
                            executed=False,
                            status="skipped (valid initial SQL)",
                            duration_ms=0.0,
                        )

                    final_sql = outcome.sql if outcome.is_valid else initial_sql
                    events.append({
                        "event": "final_result",
                        "sql": final_sql if outcome.is_valid else None,
                        "attemptsUsed": attempts_used,
                        "status": "passed" if outcome.is_valid else "failed"
                    })

                    result.local["flow"]["final"].update(
                        executed=True,
                        status="passed" if outcome.is_valid else "failed",
                        duration_ms=0.0,
                    )

                    request_total_dur = measure_ret["duration_ms"] + measure_prompt["duration_ms"] + measure_gen["duration_ms"] + measure_val["duration_ms"]
                    result.metrics.update(
                        request_latency_ms=request_total_dur,
                        validation_passed=float(outcome.is_valid),
                        self_correction_attempts_used=float(attempts_used)
                    )
                    result.local["flow"]["request"].update(executed=True, status="Success" if outcome.is_valid else "Failed", duration_ms=request_total_dur)
                    result.local.update(production_trace_events=events, final_sql=final_sql)
                    result.stopping_point = "production validated-SQL boundary"
                    if not outcome.is_valid:
                        result.status = "failed"
                        result.local["final_sql"] = None
                        result.local["failure_reason"] = "; ".join(outcome.issues) if outcome.issues else "Query failed validation and correction attempts."
                        result.local["issues"] = list(outcome.issues)
                else:
                    with self._observer.stage("request") as measure_request:
                        outcome = pipeline.run(
                            CopilotAskRequest(question=question, conversation=()),
                            trace_observer=events.append,
                        )
                    request_latency_ms = measure_request["duration_ms"]
                    attempts = next(
                        (
                            event.get("attemptsUsed")
                            for event in reversed(events)
                            if isinstance(event, dict) and isinstance(event.get("attemptsUsed"), int)
                        ),
                        None,
                    )
                    succeeded = str(getattr(outcome, "status", "")).casefold() == "success"
                    final_sql = getattr(outcome, "sql", None)
                    result.metrics.update(
                        request_latency_ms=request_latency_ms,
                        validation_passed=float(succeeded),
                    )
                    if attempts is not None:
                        result.metrics["self_correction_attempts_used"] = float(attempts)
                    result.local["flow"]["request"].update(
                        executed=True,
                        status="Success" if succeeded else "Failed",
                        duration_ms=request_latency_ms,
                    )
                    result.local.update(
                        production_trace_events=events,
                        final_sql=final_sql,
                    )
                    result.stopping_point = "production validated-SQL boundary"
                    if not succeeded:
                        result.status = "failed"

                # Extract Tables
                tables_used = _extract_tables(final_sql)
                result.tags["tables"] = ", ".join(tables_used) if tables_used else "none"
                result.tags["tables_count"] = len(tables_used)
                result.local["tables_used"] = tables_used
                result.local["tables_count"] = len(tables_used)

                val_passed = getattr(outcome, "is_valid", False) if hasattr(outcome, "is_valid") else str(getattr(outcome, "status", "")).casefold() == "success"
                sql_history_lines = [
                    "-- ====================================================================",
                    f"-- QUESTION: {question}",
                    f"-- STATUS: {result.status.upper()}",
                    f"-- VALIDATION PASSED: {'YES' if val_passed else 'NO'}",
                    "-- ====================================================================",
                    ""
                ]
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    ev_type = ev.get("event")
                    if ev_type == "initial_generation":
                        init_sql = ev.get("sql", "")
                        if hasattr(self._observer, "log_llm_span"):
                            self._observer.log_llm_span(
                                "01_initial_llm_generation",
                                prompt=ev.get("prompt", question),
                                response_text=ev.get("raw_response", init_sql),
                                model_name=ev.get("model_name", "qwen2.5-coder:7b"),
                                provider=ev.get("provider", "ollama"),
                                input_tokens=ev.get("input_tokens"),
                                output_tokens=ev.get("output_tokens"),
                            )
                        else:
                            self._observer.log_span("01_initial_llm_generation", inputs={"question": question}, outputs={"initial_sql": init_sql})
                        sql_history_lines.extend([
                            "-- --------------------------------------------------------------------",
                            "-- [STEP 1] INITIAL LLM GENERATION (Attempt 0)",
                            "-- --------------------------------------------------------------------",
                            init_sql.strip(),
                            ""
                        ])
                    elif "attempt" in ev and "sql" in ev:
                        attempt_num = ev.get("attempt", 0)
                        attempt_sql = ev.get("sql", "")
                        issues = ev.get("deterministicIssues", [])
                        critic_issues = ev.get("verifiedCriticIssues", [])
                        all_issues = issues + critic_issues
                        action = ev.get("action", "unknown")
                        self._observer.log_span(
                            f"02_validation_attempt_{attempt_num}",
                            inputs={"sql": attempt_sql},
                            attributes={"issues_count": len(all_issues), "action": action},
                            outputs={"issues_detected": all_issues, "action": action}
                        )
                        status_text = "PASSED" if action == "passed" else f"FAILED ({action})"
                        sql_history_lines.extend([
                            "-- --------------------------------------------------------------------",
                            f"-- [STEP 2.{attempt_num + 1}] VALIDATION CHECK (Attempt {attempt_num})",
                            f"-- Status: {status_text}",
                        ])
                        if all_issues:
                            sql_history_lines.append("-- Issues Detected:")
                            for issue in all_issues:
                                sql_history_lines.append(f"--   * {issue}")
                        sql_history_lines.extend([
                            "-- --------------------------------------------------------------------",
                            attempt_sql.strip(),
                            ""
                        ])
                    elif ev_type == "after_correction":
                        attempt_num = ev.get("attempt", 0)
                        corr_sql = ev.get("correctedSql", "")
                        self._observer.log_span(
                            f"03_self_correction_attempt_{attempt_num + 1}",
                            inputs={"attempt": attempt_num},
                            outputs={"corrected_sql": corr_sql}
                        )
                        sql_history_lines.extend([
                            "-- --------------------------------------------------------------------",
                            f"-- [STEP 3.{attempt_num + 1}] SELF-CORRECTION OUTPUT (Attempt {attempt_num + 1})",
                            "-- --------------------------------------------------------------------",
                            corr_sql.strip(),
                            ""
                        ])
                if final_sql:
                    sql_history_lines.extend([
                        "-- ====================================================================",
                        "-- FINAL ACCEPTED SQL QUERY:",
                        "-- ====================================================================",
                        final_sql.strip(),
                        ""
                    ])
                val_history_text = "\n".join(sql_history_lines)
                result.local["validation_history_sql"] = val_history_text
                self._observer.log_artifact_text(val_history_text, "validation_history.sql")

            indexed_after = getattr(repository, "_indexed_revision_id", None)
            result.tags.update({"index_created": indexed_before is None and indexed_after is not None, "index_reused": indexed_before == indexed_after and indexed_after is not None, "index_rebuilt": indexed_before is not None and indexed_after is not None and indexed_before != indexed_after})
            return result
        except Exception as exc:
            result.status, result.tags["error_type"], result.local["local_error"] = "failed", safe_error(exc), str(exc)
            if layer in {"retrieval", "prompt", "generation"}:
                result.local["local_diagnostic"] = backend_request_diagnostic(exc)
            return result
        finally:
            if lifecycle_cm is not None:
                try:
                    exc_type, exc_val, exc_tb = sys.exc_info()
                    lifecycle_cm.__exit__(exc_type, exc_val, exc_tb)
                except Exception:
                    pass
            if audit_ctx is not None:
                try:
                    summary = build_request_summary(audit_ctx)
                    result.local["latency_summary"] = summary
                    result.local["latency_hierarchy"] = summary.get("hierarchy", {})
                    self._enrich_flow_from_audit(result.local.get("flow", {}), audit_ctx)
                except Exception:
                    pass
            result.metrics["total_latency_ms"] = (self._clock() - started) * 1000
            result.tags.update(retrieval_metadata(repository))
            result.tags["trace_reason"] = trace_reason({**result.metrics, "status": result.status}, self._settings, developer_debug=True)
            param_keys = {
                "model_name", "model_provider", "model_runtime", "temperature",
                "context_limit", "output_limit", "prompt_name", "prompt_version",
                "prompt_hash", "semantic_revision", "embedding_provider",
                "embedding_model", "embedding_dimension", "index_identity",
                "index_type", "index_version", "top_k",
            }
            params = {k: v for k, v in result.tags.items() if k in param_keys}
            tags = {k: v for k, v in result.tags.items() if k not in param_keys}
            self._observer.log_params(params)
            self._observer.log(metrics=result.metrics, tags=tags)
            self._observer.log_artifact_dict(
                {
                    "requested_layer": result.requested_layer,
                    "status": result.status,
                    "stopping_point": result.stopping_point,
                    "metrics": result.metrics,
                    "tags": result.tags,
                    "local": result.local,
                },
                "debug_result.json",
            )
            final_sql = result.local.get("final_sql") or result.local.get("generation")
            if isinstance(final_sql, str) and final_sql.strip():
                self._observer.log_artifact_text(final_sql, "generated_sql.sql")
            self._observer.log_artifact_text(TEXT_TO_SQL_PROMPT, "prompt_template.txt")
            self._observer.finish()

    @staticmethod
    def _enrich_flow_from_audit(flow: dict[str, dict[str, Any]], audit_ctx: RequestAuditContext) -> None:
        if not flow or not audit_ctx:
            return

        span_by_name: dict[str, Any] = {s.name: s for s in audit_ctx.all_spans}

        if "request" in flow and audit_ctx.root_span:
            root = audit_ctx.root_span
            flow["request"]["inclusive_duration_ms"] = round(root.inclusive_duration_ms, 2)
            flow["request"]["exclusive_duration_ms"] = round(root.exclusive_duration_ms, 2)
            flow["request"]["child_covered_duration_ms"] = round(root.child_covered_duration_ms, 2)
            flow["request"]["orchestration_gaps_ms"] = round(root.orchestration_gaps_ms, 2)
            flow["request"]["unaccounted_ms"] = round(root.unaccounted_ms, 2)

        stage_mapping = {
            "retrieval": ("context_retrieval", "retrieval"),
            "prompt": ("prompt_construction", "prompt"),
            "generation": ("sql_generation", "generation", "llm_inference"),
            "validation": ("deterministic_validation", "validation"),
            "critic": ("critic",),
            "correction": ("self_correction", "correction"),
        }

        for stg_key, candidate_names in stage_mapping.items():
            if stg_key not in flow:
                continue
            item = flow[stg_key]
            matched_span = next((span_by_name[name] for name in candidate_names if name in span_by_name), None)
            if matched_span is not None:
                item["inclusive_duration_ms"] = round(matched_span.inclusive_duration_ms, 2)
                item["exclusive_duration_ms"] = round(matched_span.exclusive_duration_ms, 2)
                item["child_covered_duration_ms"] = round(matched_span.child_covered_duration_ms, 2)
                item["orchestration_gaps_ms"] = round(matched_span.orchestration_gaps_ms, 2)
                item["unaccounted_ms"] = round(matched_span.unaccounted_ms, 2)
            elif item.get("executed") and isinstance(item.get("duration_ms"), (int, float)):
                dur = round(float(item["duration_ms"]), 2)
                item["inclusive_duration_ms"] = dur
                item["exclusive_duration_ms"] = dur
                item["child_covered_duration_ms"] = 0.0
                item["orchestration_gaps_ms"] = 0.0
                item["unaccounted_ms"] = 0.0

    @staticmethod
    def _initial_flow(layer: str) -> dict[str, dict[str, Any]]:
        return {
            stage: {
                "executed": False,
                "status": "not_executed",
                "duration_ms": "unavailable",
                "inclusive_duration_ms": "unavailable",
                "exclusive_duration_ms": "unavailable",
                "reason": "not requested",
            }
            for stage in ("request", "retrieval", "prompt", "generation", "validation", "critic", "correction", "final")
        }
