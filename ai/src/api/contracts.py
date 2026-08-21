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
    triggerType: Literal["FullRebuild", "Incremental"]
    semanticLayerId: str = Field(min_length=1)
    sourceFileIds: dict[str, str]
    resolvedSources: dict[str, Any]
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
