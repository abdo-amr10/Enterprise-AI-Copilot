"""Exact Replay Manager providing the cheapest safe execution replay path."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Optional

from src.application.services.conversation.normalization.normalizer import RequestNormalizer
from src.application.services.conversation.replay.fingerprint import (
    RequestFingerprint,
    compute_fingerprint,
)
from src.application.services.conversation.replay.replay_cache import (
    InMemoryReplayRepository,
    ReplayEntry,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayResult:
    is_valid: bool
    entry: Optional[ReplayEntry] = None
    fingerprint: Optional[RequestFingerprint] = None
    reason_for_miss: Optional[str] = None


class ExactReplayManager:
    """Manages exact request replay before LLM, embeddings, or Text-to-SQL.

    Guarantees tenant isolation, authorization safety, revision synchronization,
    and safe negative-result isolation.
    """

    def __init__(self, repository: Optional[InMemoryReplayRepository] = None) -> None:
        self._repository = repository or InMemoryReplayRepository()

    @property
    def repository(self) -> InMemoryReplayRepository:
        return self._repository

    def lookup(
        self,
        question: str,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        semantic_revision_id: str | None = None,
        schema_version: str | None = None,
        conversation_id: str | None = None,
    ) -> ReplayResult:
        """Lookup an exact replay entry and validate all safety boundaries."""
        fingerprint = compute_fingerprint(
            question,
            tenant_id=tenant_id,
            user_id=user_id,
            semantic_revision_id=semantic_revision_id,
            schema_version=schema_version,
            conversation_id=conversation_id,
        )

        # Strictly require authenticated security context (tenant_id and user_id)
        if not tenant_id or not user_id:
            logger.info("Replay lookup bypassed: missing explicit tenant_id or user_id.")
            return ReplayResult(
                is_valid=False,
                fingerprint=fingerprint,
                reason_for_miss="MISSING_SECURITY_CONTEXT",
            )

        entry = self._repository.get(fingerprint.fingerprint_hash)
        if entry is None:
            return ReplayResult(
                is_valid=False,
                fingerprint=fingerprint,
                reason_for_miss="CACHE_ENTRY_NOT_FOUND",
            )

        # 1. Tenant boundary validation
        if entry.tenant_id != fingerprint.tenant_id:
            logger.warning("Tenant mismatch in replay cache: expected %s, got %s", fingerprint.tenant_id, entry.tenant_id)
            return ReplayResult(
                is_valid=False,
                fingerprint=fingerprint,
                reason_for_miss="TENANT_SCOPE_MISMATCH",
            )

        # 2. Authorization boundary validation
        if entry.user_id != fingerprint.user_id:
            logger.info("Authorization mismatch in replay cache: expected user %s, got %s", fingerprint.user_id, entry.user_id)
            return ReplayResult(
                is_valid=False,
                fingerprint=fingerprint,
                reason_for_miss="AUTHORIZATION_SCOPE_MISMATCH",
            )

        # 3. Semantic revision boundary validation
        if entry.semantic_revision_id != fingerprint.semantic_revision_id:
            logger.info(
                "Semantic revision mismatch in replay cache: active %s, cached %s",
                fingerprint.semantic_revision_id,
                entry.semantic_revision_id,
            )
            return ReplayResult(
                is_valid=False,
                fingerprint=fingerprint,
                reason_for_miss="SEMANTIC_REVISION_MISMATCH",
            )

        # 4. Schema version boundary validation
        if entry.schema_version != fingerprint.schema_version:
            logger.info(
                "Schema context mismatch in replay cache: active %s, cached %s",
                fingerprint.schema_version,
                entry.schema_version,
            )
            return ReplayResult(
                is_valid=False,
                fingerprint=fingerprint,
                reason_for_miss="SCHEMA_CONTEXT_MISMATCH",
            )

        # 5. Negative cache safety validation
        if entry.is_negative_result:
            # A negative result is ONLY valid for the exact same normalized query.
            # Never reuse negative results across different queries.
            if entry.normalized_question != fingerprint.normalized_question:
                return ReplayResult(
                    is_valid=False,
                    fingerprint=fingerprint,
                    reason_for_miss="NEGATIVE_RESULT_SCOPE_MISMATCH",
                )

        return ReplayResult(
            is_valid=True,
            entry=entry,
            fingerprint=fingerprint,
        )

    def record_success(
        self,
        question: str,
        sql: Optional[str],
        *,
        text_summary: Optional[str] = None,
        presentation_type: str = "DataTable",
        tenant_id: str | None = None,
        user_id: str | None = None,
        semantic_revision_id: str | None = None,
        schema_version: str | None = None,
        conversation_id: str | None = None,
        ttl_seconds: int = 3600,
        metadata: Optional[dict] = None,
    ) -> Optional[ReplayEntry]:
        """Record a successful execution for future exact replay."""
        if not tenant_id or not user_id:
            logger.debug("Exact replay caching skipped: missing explicit tenant_id or user_id.")
            return None

        fingerprint = compute_fingerprint(
            question,
            tenant_id=tenant_id,
            user_id=user_id,
            semantic_revision_id=semantic_revision_id,
            schema_version=schema_version,
            conversation_id=conversation_id,
        )

        entry = ReplayEntry(
            fingerprint=fingerprint.fingerprint_hash,
            normalized_question=fingerprint.normalized_question,
            tenant_id=fingerprint.tenant_id,
            user_id=fingerprint.user_id,
            semantic_revision_id=fingerprint.semantic_revision_id,
            schema_version=fingerprint.schema_version,
            sql=sql,
            text_summary=text_summary,
            presentation_type=presentation_type,
            is_success=True,
            is_negative_result=False,
            ttl_seconds=ttl_seconds,
            metadata=metadata or {},
        )
        self._repository.save(entry)
        return entry

    def record_negative_result(
        self,
        question: str,
        outcome_type: str,  # e.g., "NO_ROWS_FOUND"
        *,
        text_summary: Optional[str] = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        semantic_revision_id: str | None = None,
        schema_version: str | None = None,
        conversation_id: str | None = None,
        ttl_seconds: int = 300,  # Shorter TTL for negative results
        metadata: Optional[dict] = None,
    ) -> Optional[ReplayEntry]:
        """Record a negative result (e.g. 0 rows) with strict isolation."""
        if not tenant_id or not user_id:
            logger.debug("Negative replay caching skipped: missing explicit tenant_id or user_id.")
            return None

        fingerprint = compute_fingerprint(
            question,
            tenant_id=tenant_id,
            user_id=user_id,
            semantic_revision_id=semantic_revision_id,
            schema_version=schema_version,
            conversation_id=conversation_id,
        )

        entry = ReplayEntry(
            fingerprint=fingerprint.fingerprint_hash,
            normalized_question=fingerprint.normalized_question,
            tenant_id=fingerprint.tenant_id,
            user_id=fingerprint.user_id,
            semantic_revision_id=fingerprint.semantic_revision_id,
            schema_version=fingerprint.schema_version,
            sql=None,
            text_summary=text_summary,
            presentation_type="DirectAnswer",
            is_success=True,
            is_negative_result=True,
            negative_outcome_type=outcome_type,
            ttl_seconds=ttl_seconds,
            metadata=metadata or {},
        )
        self._repository.save(entry)
        return entry
