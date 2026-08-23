"""Pydantic contracts for the AI runtime HTTP boundary."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CopilotRequest(StrictModel):
    question: str = Field(min_length=1)
    conversation: list[dict[str, Any]] = Field(default_factory=list)


class CopilotResponse(StrictModel):
    status: Literal["Success", "Failed"]
    sql: str | None
    errorCode: str | None = None
    message: str | None = None
    failureReason: str | None = None
    rewrittenQuestion: str | None = None
    suggestions: list[str] = Field(default_factory=list)


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
    draft: dict[str, Any]
    schema: dict[str, Any]
    relationships: list[dict[str, Any]] = Field(default_factory=list)


class SemanticReviewRequest(StrictModel):
    draft: dict[str, Any]
    validation: dict[str, Any]
    decision: Literal["Approve", "Reject"]
    reviewerId: str = Field(min_length=1)
    comments: str = ""


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
    executionResult: ExecutionResultRequest
