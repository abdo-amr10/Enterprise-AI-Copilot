"""Pydantic contracts for the AI runtime HTTP boundary."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, protected_namespaces=())


class CopilotRequest(StrictModel):
    question: str = Field(min_length=1)
    conversation: list[dict[str, Any]] = Field(default_factory=list)


class CopilotResponse(StrictModel):
    """Response contract consumed by the .NET ``AiRuntimeResponse`` DTO."""

    isSuccess: bool
    generatedSql: str | None = None
    textSummary: str | None = None
    presentationType: str = "DataTable"
    errorMessage: str | None = None


class SemanticRetrieveRequest(CopilotRequest):
    top_k: int | None = Field(default=None, gt=0)


class AffectedObjectRequest(StrictModel):
    section: Literal["entities", "relationships", "measures", "dimensions", "business_rules"]
    action: Literal["add", "update", "delete"] = "update"
    id: str | None = None
    name: str | None = None


class SemanticGenerateRequest(StrictModel):
    """Backend-to-AI generation request.

    ``revisionId`` is intentionally absent. The Backend allocates the
    revision only after persisting the AI-produced draft.
    """

    triggerType: Literal["FullRebuild", "Incremental"]
    semanticLayerId: str = Field(min_length=1)
    # Schema is mandatory. Optional source types may be represented as null
    # by Backend JSON serializers and are removed before AI ingestion.
    sourceFileIds: dict[str, str | None]
    baseRevisionId: str | None = None
    baseSemanticLayer: dict[str, Any] | None = None
    affectedObjects: list[AffectedObjectRequest] = Field(default_factory=list)


class SemanticValidateRequest(StrictModel):
    """Support both Backend acknowledgement and in-memory coverage validation.

    The current Backend submits a persisted ``revisionId`` only. Direct AI
    callers may instead provide a draft plus its authoritative schema to run
    the full coverage validator. At least one of these forms is required by
    the router.
    """

    revisionId: str | None = Field(default=None, min_length=1)
    draft: dict[str, Any] | None = None
    schema: dict[str, Any] | None = None
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    documentation: str | None = None
    businessGlossary: str | None = None


class SemanticReviewRequest(StrictModel):
    """Backend-to-AI review acknowledgement request.

    The Backend owns revision persistence, validation state, the authenticated
    reviewer, and the final status transition. It sends only the revision ID
    and the human decision to this internal endpoint.
    """

    revisionId: str = Field(min_length=1)
    decision: Literal["Approve", "Reject"]
    comments: str | None = None


class ExecutionResultRequest(StrictModel):
    """Backend result payload supplied after Backend-owned SQL execution."""

    status: Literal["Success", "Failed"]
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    rowCount: int | None = Field(default=None, ge=0)
    errorCode: str | None = None
    errorMessage: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PostQueryFormatRequest(StrictModel):
    question: str = Field(min_length=1)
    executionResult: ExecutionResultRequest | list[dict[str, Any]]


class DebugRunRequest(StrictModel):
    question: str = Field(min_length=1)
    layer: Literal["full", "retrieval", "prompt", "generation", "validation", "critic", "correction"] = "full"
    show_local_output: bool = True

