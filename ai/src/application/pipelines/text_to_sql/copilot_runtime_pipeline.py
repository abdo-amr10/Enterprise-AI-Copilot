"""Translate a Copilot question into safe, backend-executable read-only SQL."""

from __future__ import annotations

import json
import re
import logging
from collections.abc import Callable
from typing import Any

import uuid
from src.observability.mlflow_observer import MLflowObserver
from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.backend.copilot.text_to_sql_runtime_response import (
    TextToSQLRuntimeResponse,
)
from src.application.services.self_correction.self_correction_service import (
    SelfCorrectionService,
)
from src.application.services.text_to_sql.text_to_sql_pipeline import TextToSQLPipeline

logger = logging.getLogger(__name__)


class CopilotRuntimePipeline:
    """AI orchestration pipeline for Natural Language to SQL generation.

    Coordinates read-only intent validation, context retrieval, initial SQL generation,
    and self-correction loops with fail-safe MLflow tracing and correlation metadata.
    This pipeline never connects to SQL Server or executes queries; it generates and
    validates SQL candidate strings to hand off to the Backend.
    """

    @staticmethod
    def _parse_generation_response(text: str) -> dict:
        """Parse structured JSON payload from the raw LLM generation response.

        Args:
            text: Raw string output from the LLM.

        Returns:
            Parsed JSON dictionary.

        Raises:
            ValueError: If the text is not a valid JSON object.
        """
        cleaned = text.strip()

        # Remove Markdown code fences if the model wraps JSON in them.
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        try:
            payload = json.loads(cleaned)
        except Exception:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                payload = json.loads(cleaned[start : end + 1])
            else:
                raise ValueError("LLM response must be a JSON object.")

        if not isinstance(payload, dict):
            raise ValueError("LLM response must be a JSON object.")

        return payload

    _FORBIDDEN_SQL = re.compile(
        r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|"
        r"EXEC(?:UTE)?|SELECT\s+INTO|USE|GRANT|REVOKE|DENY|DBCC|BACKUP|RESTORE)\b",
        re.IGNORECASE,
    )
    _WRITE_INTENT = re.compile(
        r"\b(insert|add|create|update|edit|modify|delete|remove|drop|alter|truncate)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        text_to_sql_pipeline: TextToSQLPipeline,
        self_correction_service: SelfCorrectionService,
        observer: MLflowObserver | None = None,
    ) -> None:
        """Initialize the Copilot runtime pipeline.

        Args:
            text_to_sql_pipeline: Initial generation pipeline handling context & prompt.
            self_correction_service: Deterministic and LLM self-correction service.
            observer: Optional MLflow observer for diagnostic telemetry and tracing.
        """
        self._text_to_sql_pipeline = text_to_sql_pipeline
        self._self_correction_service = self_correction_service
        self._observer = observer

    def run(
        self,
        request: CopilotAskRequest,
        trace_observer: Callable[[dict[str, Any]], None] | None = None,
    ) -> TextToSQLRuntimeResponse:
        """Process a natural language question into a validated read-only SQL query.

        Args:
            request: The Copilot ask request containing question and conversation history.
            trace_observer: Optional callback for streaming diagnostic telemetry events.

        Returns:
            TextToSQLRuntimeResponse with success status and SQL string, or failure details.
        """
        correlation_id = getattr(request, "correlation_id", None)
        traceparent = getattr(request, "traceparent", None)
        ai_trace_id = str(uuid.uuid4())

        observer = self._observer or MLflowObserver()
        tags: dict[str, Any] = {
            "ai_trace_id": ai_trace_id,
            "pipeline": "CopilotRuntimePipeline",
        }
        if correlation_id:
            tags["correlation_id"] = correlation_id
        if traceparent:
            tags["traceparent"] = traceparent

        try:
            observer.start(tags=tags)
        except Exception as exc:
            logger.warning("MLflow trace start failed: %s", exc)

        response: TextToSQLRuntimeResponse | None = None
        try:
            if self._WRITE_INTENT.search(request.question):
                response = TextToSQLRuntimeResponse.failure(
                    "READ_ONLY_REQUEST_REQUIRED",
                    "This Copilot supports read-only questions only.",
                    failure_reason=(
                        "The request asks to create, modify, or delete data. "
                        "INSERT, UPDATE, DELETE, and other write operations are not supported."
                    ),
                    suggestions=(
                        "Ask to view or summarize existing data instead.",
                    ),
                )
                return response

            try:
                with observer.stage("context_retrieval"):
                    semantic_context = self._text_to_sql_pipeline.build_context(request.question)
                correction_feedback = "\n".join(
                    str(message.get("content", ""))
                    for message in request.conversation
                    if message.get("role") == "system"
                    and str(message.get("content", "")).startswith("RLS_CORRECTION:")
                )
                conversation_context = "\n".join(
                    f"{message.get('role', 'user')}: {message.get('content', '')}"
                    for message in request.conversation
                    if message.get("role") in ("user", "assistant")
                )
                with observer.stage("llm_generation"):
                    try:
                        generated = self._text_to_sql_pipeline.run(
                            question=request.question,
                            semantic_context=semantic_context,
                            correction_feedback=correction_feedback,
                            conversation_context=conversation_context,
                        )
                    except TypeError:
                        generated = self._text_to_sql_pipeline.run(
                            question=request.question,
                            semantic_context=semantic_context,
                            correction_feedback=correction_feedback,
                        )

                try:
                    if hasattr(observer, "log_llm_span"):
                        observer.log_llm_span(
                            "llm_sql_generation",
                            prompt=request.question,
                            response_text=generated.text,
                            model_name=getattr(generated, "model_name", None) or "qwen2.5-coder:7b",
                            provider=getattr(generated, "provider", None) or "ollama",
                            input_tokens=getattr(generated, "input_tokens", None),
                            output_tokens=getattr(generated, "output_tokens", None),
                        )
                except Exception as span_exc:
                    logger.debug("Failed logging LLM span: %s", span_exc)
            except Exception as exc:
                logger.exception("Text-to-SQL generation failed")
                response = TextToSQLRuntimeResponse.failure(
                    "SQL_GENERATION_FAILED",
                    "The system could not generate SQL for this request.",
                    failure_reason=f"Generation service failed: {type(exc).__name__}: {exc}",
                )
                return response

            try:
                payload = self._parse_generation_response(generated.text)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.info("Generated model output was not a valid structured response: %s", exc)
                response = TextToSQLRuntimeResponse.failure(
                    "INVALID_MODEL_OUTPUT",
                    "The model response was not a valid structured SQL result.",
                    failure_reason="The generation model did not return the required JSON SQL contract.",
                )
                return response

            model_status = str(payload.get("status", "")).strip().lower()

            # Handle 'needs_clarification' explicitly with ZERO SQL execution or validation
            if model_status == "needs_clarification":
                warnings = payload.get("warnings") or []
                suggestions = tuple(str(s) for s in warnings) if isinstance(warnings, list) else ()
                reason = "; ".join(suggestions) if suggestions else "The model requested clarification."
                logger.info("Generated model output requested clarification: %s", reason)
                response = TextToSQLRuntimeResponse.failure(
                    "NEEDS_CLARIFICATION",
                    "The request cannot be translated into a safe query without more information.",
                    failure_reason=reason,
                    suggestions=suggestions,
                )
                return response

            # Handle 'unsafe_request' explicitly
            if model_status == "unsafe_request":
                warnings = payload.get("warnings") or []
                reason = "; ".join(str(w) for w in warnings) if isinstance(warnings, list) else "The request was deemed unsafe."
                logger.info("Generated model output flagged unsafe request: %s", reason)
                response = TextToSQLRuntimeResponse.failure(
                    "UNSAFE_REQUEST",
                    "The requested operation is not allowed.",
                    failure_reason=reason,
                )
                return response

            if model_status not in ("success", "ok", "valid", "complete", "done", ""):
                logger.info("Generated model output returned unexpected status: %s", model_status)
                response = TextToSQLRuntimeResponse.failure(
                    "INVALID_MODEL_OUTPUT",
                    f"Unexpected model status '{model_status}'.",
                    failure_reason=f"The model returned an unknown status code '{model_status}' in its JSON payload.",
                )
                return response

            sql = payload.get("sql")
            if not isinstance(sql, str) or not sql.strip():
                logger.info("Model success payload missing SQL string")
                response = TextToSQLRuntimeResponse.failure(
                    "INVALID_MODEL_OUTPUT",
                    "The system could not generate a SQL query.",
                    failure_reason="The generation model returned success status but missing or null SQL.",
                )
                return response

            if payload.get("is_read_only") is not True or self._FORBIDDEN_SQL.search(sql):
                logger.info("Generated model output was unsafe or not read-only")
                response = TextToSQLRuntimeResponse.failure(
                    "SQL_VALIDATION_FAILED",
                    "The system could not generate a safe read-only query for this request.",
                    failure_reason=(
                        "The generated payload was not marked read-only or contained a forbidden operation."
                    ),
                )
                return response

            sql = sql.strip()

            logger.info("INITIAL_GENERATION SQL: %s", sql)

            self._notify_trace_observer(
                trace_observer,
                {"event": "initial_generation", "sql": sql},
            )

            try:
                correction_kwargs: dict[str, Any] = {
                    "question": request.question,
                    "sql": sql,
                    "semantic_context": semantic_context,
                    # The Backend requires its bound parameter for every
                    # executable query. Enforce the same policy on the initial
                    # attempt so correction happens in AI before Swagger reaches
                    # the Backend executor.
                    "enforce_rls": True,
                }
                if trace_observer is not None:
                    correction_kwargs["trace_observer"] = trace_observer

                with observer.stage("self_correction"):
                    outcome = self._self_correction_service.run(**correction_kwargs)
            except Exception as exc:
                logger.exception("Text-to-SQL validation/correction failed")
                response = TextToSQLRuntimeResponse.failure(
                    "SQL_VALIDATION_FAILED",
                    "The system could not validate the generated SQL.",
                    failure_reason=f"Validation service failed: {type(exc).__name__}: {exc}",
                )
                return response

            if not outcome.is_valid:
                self._notify_trace_observer(
                    trace_observer,
                    {
                        "event": "final_result",
                        "sql": None,
                        "attemptsUsed": outcome.attempts_used,
                        "status": "failed",
                        "issues": list(outcome.issues),
                    },
                )
                is_oscillation = any("CORRECTION_OSCILLATION" in str(iss) or "oscillat" in str(iss).lower() for iss in outcome.issues)
                error_code = "CORRECTION_OSCILLATION" if is_oscillation else "MAX_RETRIES_EXCEEDED"
                response = TextToSQLRuntimeResponse.failure(
                    error_code,
                    "The system could not generate a valid read-only SQL query.",
                    failure_reason="; ".join(outcome.issues) or "The query remained invalid after correction attempts.",
                )
                return response

            self._notify_trace_observer(
                trace_observer,
                {
                    "event": "final_result",
                    "sql": outcome.sql,
                    "attemptsUsed": outcome.attempts_used,
                    "status": "passed",
                },
            )
            response = TextToSQLRuntimeResponse.success(outcome.sql)
            return response
        finally:
            try:
                status_str = (
                    "SUCCESS"
                    if response is not None and response.status == "Success"
                    else "FAILURE"
                )
                observer.log(
                    tags={
                        "runtime_status": status_str,
                        "error_code": (
                            response.error_code
                            if response and response.error_code
                            else "NONE"
                        ),
                    }
                )
                observer.finish()
            except Exception as exc:
                logger.warning("MLflow trace finish failed: %s", exc)

    @staticmethod
    def _notify_trace_observer(
        trace_observer: Callable[[dict[str, Any]], None] | None,
        event: dict[str, Any],
    ) -> None:
        """Publish optional diagnostics without changing the runtime response."""

        if trace_observer is None:
            return
        try:
            trace_observer(dict(event))
        except Exception:
            logger.warning("Text-to-SQL trace observer failed", exc_info=True)
