"""Orchestrates Hybrid Self-Correction for a generated SQL query.

Flow (matches the agreed design exactly):

    generated SQL
        -> Syntax Validator      (deterministic)
        -> Schema Validator      (deterministic)
        -> Relationship Validator(deterministic)
        -> [only if all three pass] SQL Critic (LLM, diagnosis only)
        -> CriticFindingVerifier (deterministic -- filters hallucinated findings)
        -> [only if issues remain] SQL Correction (LLM, fixes only those issues)
        -> re-validate from the top
        -> up to max_attempts corrections, then FAILED

The LLM never has the final word: every correction is re-validated
deterministically before it can be accepted, and critic findings are
never acted on unless CriticFindingVerifier can ground them in the
approved schema/relationships.

Semantic context is retrieved once per request (via the existing
ContextRetrievalService, not re-implemented here) and reused across
every attempt in the loop, per the "retrieve once" principle.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.application.ports.physical_schema_repository import PhysicalSchemaRepository
from src.application.services.self_correction.critic_finding_verifier import (
    CriticFindingVerifier,
)
from src.application.dto.self_correction.self_correction_outcome import (
    SelfCorrectionOutcome,
)
from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.application.services.self_correction.sql_correction_service import SQLCorrectionService
from src.application.services.self_correction.sql_critic_service import SQLCriticService
from src.application.services.self_correction.validators.sql_relationship_validator import (
    SQLRelationshipValidator,
)
from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)
from src.application.services.self_correction.validators.sql_rls_validator import SQLRlsValidator
from src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)

logger = logging.getLogger(__name__)

TraceObserver = Callable[[dict[str, Any]], None]


class SelfCorrectionService:
    """Orchestrates deterministic-first, LLM-assisted SQL self-correction.

    Validates candidate SQL through a strict order:
        1. SQLSyntaxValidator (Deterministic AST / Read-only parser)
        2. SQLSchemaValidator (Deterministic Physical Schema verification)
        3. SQLRelationshipValidator (Deterministic Semantic Relationship verification)
        4. SQLRlsValidator (Deterministic Parameterized RLS mapping check)
        5. SQLCriticService (LLM critic - advisory only)
        6. CriticFindingVerifier (Deterministic evidence grounding check)
        7. SQLCorrectionService (LLM correction for validated issues only)

    Re-validates all corrections from step 1 up to max_attempts bounded iterations.
    """

    def __init__(
        self,
        context_retrieval_service: ContextRetrievalService,
        syntax_validator: SQLSyntaxValidator,
        schema_validator: SQLSchemaValidator,
        relationship_validator: SQLRelationshipValidator,
        critic_service: SQLCriticService,
        finding_verifier: CriticFindingVerifier,
        correction_service: SQLCorrectionService,
        max_attempts: int = 3,
        rls_validator: SQLRlsValidator | None = None,
        schema_provider: PhysicalSchemaRepository | None = None,
    ) -> None:
        """Initialize the SelfCorrectionService.

        Args:
            context_retrieval_service: Service for retrieving semantic slices.
            syntax_validator: Deterministic T-SQL parser and safety validator.
            schema_validator: Deterministic database schema validator.
            relationship_validator: Deterministic JOIN relationship validator.
            critic_service: LLM critic service for semantic evaluation.
            finding_verifier: Deterministic verifier grounding critic claims.
            correction_service: LLM correction service.
            max_attempts: Maximum allowed correction iterations (default: 3).
            rls_validator: Optional deterministic RLS join mapping validator.
            schema_provider: Optional physical database schema repository.
        """
        self._context_retrieval_service = context_retrieval_service
        self._syntax_validator = syntax_validator
        self._schema_validator = schema_validator
        self._relationship_validator = relationship_validator
        self._critic_service = critic_service
        self._finding_verifier = finding_verifier
        self._correction_service = correction_service
        self._max_attempts = max_attempts
        self._rls_validator = rls_validator
        self._schema_provider = schema_provider or getattr(
            schema_validator, "_schema_provider", None
        )

    def run(
        self,
        question: str,
        sql: str,
        semantic_context: str | None = None,
        trace_observer: TraceObserver | None = None,
        enforce_rls: bool = False,
    ) -> SelfCorrectionOutcome:
        """Validate candidate SQL and run bounded correction loops if defects exist.

        Args:
            question: User's natural language question.
            sql: Initial candidate SQL statement string.
            semantic_context: Optional pre-retrieved semantic context.
            trace_observer: Optional callback for diagnostic telemetry logging.
            enforce_rls: Whether to enforce parameterized RLS join policies.

        Returns:
            SelfCorrectionOutcome containing validity status, final SQL, attempts used,
            and complete trace history.
        """
        semantic_context = semantic_context or self._context_retrieval_service.build_llm_context(question)
        current_sql = sql
        last_issues: list[ValidationIssue] = []
        trace: list[dict[str, object]] = []
        corrections_used = 0
        cached_schema: dict[str, Any] | None = None

        def _get_schema() -> dict[str, Any]:
            nonlocal cached_schema
            if cached_schema is None:
                if self._schema_provider is not None:
                    cached_schema = self._schema_provider.get_schema()
                elif hasattr(self._schema_validator, "_schema_provider") and self._schema_validator._schema_provider is not None:
                    cached_schema = self._schema_validator._schema_provider.get_schema()
                else:
                    cached_schema = {}
            return cached_schema

        for attempt in range(self._max_attempts + 1):
            logger.info("Self-correction attempt %s", attempt)
            issues = self._deterministic_issues(current_sql, _get_schema, enforce_rls=enforce_rls)
            trace.append({
                "attempt": attempt,
                "sql": current_sql,
                "deterministicIssues": [issue.message for issue in issues],
            })

            if not issues:
                critic_result = self._critic_service.evaluate(
                    question=question,
                    sql=current_sql,
                    semantic_context=semantic_context,
                )
                try:
                    issues = self._finding_verifier.verify(critic_result, schema=_get_schema())
                except TypeError:
                    issues = self._finding_verifier.verify(critic_result)
                trace[-1]["criticStatus"] = critic_result.status
                trace[-1]["verifiedCriticIssues"] = [issue.message for issue in issues]

            if not issues:
                logger.info("Validation passed on attempt %s", attempt)
                self._notify_trace_observer(
                    trace_observer, {**trace[-1], "action": "passed"}
                )
                return SelfCorrectionOutcome.success(
                    current_sql, attempts_used=attempt, trace=tuple(trace)
                )

            last_issues = issues

            for issue in issues:
                logger.info("Validation issue [%s]: %s", issue.type, issue.message)

            if attempt == self._max_attempts:
                logger.info("Self-correction stopped: maximum attempts (%s) reached", self._max_attempts)
                self._notify_trace_observer(
                    trace_observer,
                    {**trace[-1], "action": "maximum_attempts_reached"},
                )
                break

            self._notify_trace_observer(
                trace_observer,
                {**trace[-1], "action": "correction_required"},
            )

            try:
                corrections_used += 1
                corrected_sql = self._correction_service.correct(
                    question=question,
                    current_sql=current_sql,
                    issues=issues,
                    relevant_schema=self._relevant_schema(current_sql, _get_schema),
                    relevant_relationships=self._relevant_relationships(current_sql, _get_schema),
                )
            except Exception as exc:
                logger.warning("SQL correction call failed: %s", type(exc).__name__)
                trace[-1]["correctionError"] = type(exc).__name__
                self._notify_trace_observer(
                    trace_observer,
                    {
                        "event": "correction_failed",
                        "attempt": attempt + 1,
                        "error": type(exc).__name__,
                    },
                )
                break

            if not corrected_sql:
                logger.info("Self-correction stopped: correction model returned no SQL")
                self._notify_trace_observer(
                    trace_observer,
                    {"event": "correction_returned_no_sql", "attempt": attempt + 1},
                )
                break

            logger.info("SQL correction generated for attempt %s", attempt + 1)
            trace[-1]["correctedSql"] = corrected_sql
            self._notify_trace_observer(
                trace_observer,
                {
                    "event": "after_correction",
                    "attempt": attempt + 1,
                    "previousSql": current_sql,
                    "sql": corrected_sql,
                    "changed": corrected_sql != current_sql,
                },
            )
            current_sql = corrected_sql

        return SelfCorrectionOutcome.failure(
            attempts_used=corrections_used,
            issues=tuple(issue.message for issue in last_issues),
            trace=tuple(trace),
        )

    @staticmethod
    def _notify_trace_observer(
        trace_observer: TraceObserver | None,
        step: dict[str, Any],
    ) -> None:
        """Publish optional diagnostic data without affecting correction behavior."""

        if trace_observer is None:
            return
        try:
            trace_observer(dict(step))
        except Exception:
            logger.warning("Self-correction trace observer failed", exc_info=True)

    def _deterministic_issues(
        self,
        sql: str,
        schema_getter: Callable[[], dict[str, Any]] | None = None,
        enforce_rls: bool = False,
    ) -> list[ValidationIssue]:
        schema = schema_getter() if schema_getter is not None else None
        for validator in (
            self._syntax_validator,
            self._schema_validator,
            self._relationship_validator,
            *(([self._rls_validator]) if self._rls_validator is not None else []),
        ):
            try:
                result = validator.validate(sql, schema=schema, enforce_presence=enforce_rls)
            except TypeError:
                try:
                    result = validator.validate(sql, schema=schema)
                except TypeError:
                    result = validator.validate(sql)
            if not result.is_valid:
                # Stop at the first failing layer: an invalid JOIN cannot be
                # judged reliably before syntax/schema are already correct.
                return list(result.issues)
        return []

    def _relevant_schema(
        self,
        sql: str,
        schema_getter: Callable[[], dict[str, Any]] | None = None,
    ) -> dict:
        schema = schema_getter() if schema_getter is not None else None
        try:
            return self._schema_validator.schema_slice(sql, schema=schema)
        except TypeError:
            try:
                return self._schema_validator.schema_slice(sql)
            except Exception:
                return {}
        except Exception:
            # SQL could not be parsed (e.g. a syntax-error attempt): fall
            # back to no schema slice rather than failing the correction call.
            return {}

    def _relevant_relationships(
        self,
        sql: str,
        schema_getter: Callable[[], dict[str, Any]] | None = None,
    ) -> list[dict]:
        schema = schema_getter() if schema_getter is not None else None
        try:
            tables = self._schema_validator.extract_tables(sql, schema=schema)
        except TypeError:
            try:
                tables = self._schema_validator.extract_tables(sql)
            except Exception:
                return []
        except Exception:
            return []
        return self._relationship_validator.relationships_for_tables(tables)
