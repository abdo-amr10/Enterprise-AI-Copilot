"""Deterministic request fingerprinting for safe exact replay."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from src.application.services.conversation.normalization.normalizer import RequestNormalizer


@dataclass(frozen=True)
class RequestFingerprint:
    fingerprint_hash: str
    normalized_question: str
    tenant_id: str | None
    user_id: str | None
    semantic_revision_id: str
    schema_version: str
    conversation_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint_hash": self.fingerprint_hash,
            "normalized_question": self.normalized_question,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "semantic_revision_id": self.semantic_revision_id,
            "schema_version": self.schema_version,
            "conversation_id": self.conversation_id,
        }


def compute_fingerprint(
    question: str,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    semantic_revision_id: str | None = None,
    schema_version: str | None = None,
    conversation_id: str | None = None,
) -> RequestFingerprint:
    """Compute a deterministic hash fingerprint for exact request replay.

    Incorporates question semantics, tenant isolation, authorization scope,
    semantic layer revision, schema context, and conversation boundary.
    Missing security context produces a fingerprint with None identities.
    """
    normalized = RequestNormalizer.normalize(question)

    effective_tenant = str(tenant_id).strip() if tenant_id is not None and str(tenant_id).strip() else None
    effective_user = str(user_id).strip() if user_id is not None and str(user_id).strip() else None
    effective_revision = str(semantic_revision_id).strip() if semantic_revision_id is not None and str(semantic_revision_id).strip() else "active"
    effective_schema = str(schema_version).strip() if schema_version is not None and str(schema_version).strip() else "default_schema"
    effective_conversation = str(conversation_id).strip() if conversation_id is not None and str(conversation_id).strip() else ""

    payload = {
        "q": normalized,
        "t": effective_tenant,
        "u": effective_user,
        "rev": effective_revision,
        "sch": effective_schema,
        "conv": effective_conversation,
    }

    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fingerprint_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    return RequestFingerprint(
        fingerprint_hash=fingerprint_hash,
        normalized_question=normalized,
        tenant_id=effective_tenant,
        user_id=effective_user,
        semantic_revision_id=effective_revision,
        schema_version=effective_schema,
        conversation_id=effective_conversation,
    )
