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

    def run(self, question: str, sql: str, semantic_context: str | None = None) -> SelfCorrectionOutcome:
        """Validate the original candidate plus at most ``max_attempts`` corrections."""
        semantic_context = semantic_context or self._context_retrieval_service.build_llm_context(question)
        current_sql = sql

        for attempt in range(self._max_attempts + 1):
            issues = self._deterministic_issues(current_sql)

            if not issues:
                critic_result = self._critic_service.evaluate(
                    question=question,
                    sql=current_sql,
                    semantic_context=semantic_context,
                )
                issues = self._finding_verifier.verify(critic_result)

            if not issues:
                return SelfCorrectionOutcome.success(current_sql, attempts_used=attempt)

            if attempt == self._max_attempts:
                break

            corrected_sql = self._correction_service.correct(
                question=question,
                current_sql=current_sql,
                issues=issues,
                relevant_schema=self._relevant_schema(current_sql),
                relevant_relationships=self._relevant_relationships(current_sql),
            )

            if not corrected_sql:
                break

            current_sql = corrected_sql

        return SelfCorrectionOutcome.failure(attempts_used=self._max_attempts)

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
