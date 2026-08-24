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
import re
from collections.abc import Callable
from typing import Any

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
from src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)

logger = logging.getLogger(__name__)

TraceObserver = Callable[[dict[str, Any]], None]


class SelfCorrectionService:
    """Runs the deterministic-first, LLM-assisted Self-Correction loop."""

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
    ) -> None:
        self._context_retrieval_service = context_retrieval_service
        self._syntax_validator = syntax_validator
        self._schema_validator = schema_validator
        self._relationship_validator = relationship_validator
        self._critic_service = critic_service
        self._finding_verifier = finding_verifier
        self._correction_service = correction_service
        self._max_attempts = max_attempts

    def run(
        self,
        question: str,
        sql: str,
        semantic_context: str | None = None,
        trace_observer: TraceObserver | None = None,
    ) -> SelfCorrectionOutcome:
        """Validate the original candidate plus at most ``max_attempts`` corrections."""
        semantic_context = semantic_context or self._context_retrieval_service.build_llm_context(question)
        current_sql = sql
        last_issues: list[ValidationIssue] = []
        trace: list[dict[str, object]] = []
        corrections_used = 0

        for attempt in range(self._max_attempts + 1):
            logger.info("Self-correction attempt %s", attempt)
            issues = self._deterministic_issues(current_sql)
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
                    relevant_schema=self._relevant_schema(current_sql),
                    relevant_relationships=self._relevant_relationships(current_sql),
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

    def _deterministic_issues(self, sql: str) -> list[ValidationIssue]:
        for validator in (
            self._syntax_validator,
            self._schema_validator,
            self._relationship_validator,
        ):
            result = validator.validate(sql)
            if not result.is_valid:
                # Stop at the first failing layer: an invalid JOIN cannot be
                # judged reliably before syntax/schema are already correct.
                return list(result.issues)
        return self._rls_issues(sql)

    @staticmethod
    def _rls_issues(sql: str) -> list[ValidationIssue]:
        """Apply the Backend's banking RLS paths before returning SQL to it.

        This keeps invalid branch-scoped SQL inside the AI correction loop,
        where the correction model receives a concrete, deterministic error,
        instead of relying solely on a later Backend retry.
        """
        normalized = re.sub(r"\s+", " ", sql.upper())

        def issue(message: str) -> list[ValidationIssue]:
            return [ValidationIssue("rls", message, "rls_validator")]

        def has_branch_filter(*aliases: str) -> bool:
            names = "|".join(re.escape(alias) for alias in aliases)
            return bool(
                re.search(
                    rf"(?:{names})\.BRANCH_ID\s*=\s*@USERBRANCHID\b",
                    normalized,
                )
            )

        if "@USERBRANCHID" not in normalized:
            return issue("Query must include @UserBranchId in its WHERE clause.")

        if "LOANS" in normalized:
            has_required_path = all(
                fragment in normalized
                for fragment in ("JOIN CUSTOMERS", "JOIN ACCOUNTS", "JOIN BRANCHES")
            )
            has_branch_filter = has_branch_filter("B", "BRANCHES")
            if not has_required_path or not has_branch_filter:
                return issue(
                    "For loans, use exactly the RLS path loans -> customers -> "
                    "accounts -> branches and filter b.branch_id = @UserBranchId."
                )

        if "MERCHANTS" in normalized:
            if (
                "JOIN TRANSACTIONS" not in normalized
                or "JOIN ACCOUNTS" not in normalized
                or not has_branch_filter("A", "ACCOUNTS")
            ):
                return issue(
                    "For merchants, join merchants -> transactions -> accounts "
                    "and filter a.branch_id = @UserBranchId."
                )

        if "CUSTOMERS" in normalized and "LOANS" not in normalized:
            if (
                "JOIN ACCOUNTS" not in normalized
                or not has_branch_filter("A", "ACCOUNTS")
            ):
                return issue(
                    "For customers, join customers -> accounts and filter "
                    "a.branch_id = @UserBranchId."
                )

        if (
            ("TRANSACTIONS" in normalized and "MERCHANTS" not in normalized)
            or "CARDS" in normalized
        ):
            if (
                "JOIN ACCOUNTS" not in normalized
                or not has_branch_filter("A", "ACCOUNTS")
            ):
                return issue(
                    "For transactions or cards, join the table -> accounts and "
                    "filter a.branch_id = @UserBranchId."
                )

        if "ACCOUNTS" in normalized and not any(
            table in normalized
            for table in ("LOANS", "CUSTOMERS", "TRANSACTIONS", "CARDS", "MERCHANTS")
        ):
            if not has_branch_filter("A", "ACCOUNTS"):
                return issue(
                    "For accounts, filter accounts.branch_id = @UserBranchId."
                )

        if "BRANCHES" in normalized and "LOANS" not in normalized:
            if not has_branch_filter("B", "BRANCHES"):
                return issue(
                    "For branches, filter branches.branch_id = @UserBranchId."
                )

        return []

    def _relevant_schema(self, sql: str) -> dict:
        try:
            return self._schema_validator.schema_slice(sql)
        except Exception:
            # SQL could not be parsed (e.g. a syntax-error attempt): fall
            # back to no schema slice rather than failing the correction call.
            return {}

    def _relevant_relationships(self, sql: str) -> list[dict]:
        try:
            tables = self._schema_validator.extract_tables(sql)
        except Exception:
            return []
        return self._relationship_validator.relationships_for_tables(tables)
