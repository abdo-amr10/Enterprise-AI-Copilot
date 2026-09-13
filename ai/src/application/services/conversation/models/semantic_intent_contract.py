"""Structured Semantic Contract for the Conversation Layer.

Provides explicit, strongly-typed Pydantic models for semantic turn interpretation.
Semantic meaning expresses what the user conceptually wants (intent, filters, sort,
limit, temporal constraints), decoupled from physical SQL generation or schema authority.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator


class FilterSpec(BaseModel):
    target: str
    operator: Literal[
        "eq",
        "neq",
        "gt",
        "gte",
        "lt",
        "lte",
        "like",
        "in",
        "between",
        "=",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
    ] = "eq"
    value: Any

    @field_validator("operator", mode="before")
    @classmethod
    def _normalize_op(cls, v: Any) -> str:
        mapping = {
            "=": "eq",
            "==": "eq",
            "!=": "neq",
            "<>": "neq",
            ">": "gt",
            ">=": "gte",
            "<": "lt",
            "<=": "lte",
        }
        if isinstance(v, str):
            clean = v.strip().lower()
            return mapping.get(clean, clean)
        return "eq"


class SortSpec(BaseModel):
    target: Optional[str] = None
    direction: Literal["ASC", "DESC", "asc", "desc"] = "ASC"


class TimeSpec(BaseModel):
    source_text: str
    type: Literal[
        "date",
        "datetime",
        "date_range",
        "duration",
        "relative",
    ]
    start: Optional[str] = None
    end: Optional[str] = None
    timex: Optional[str] = None


class SemanticTurnIntent(BaseModel):
    action: Literal[
        "NEW_QUERY",
        "MODIFY_QUERY",
        "CLARIFICATION_ANSWER",
        "RESET",
    ]

    target_entity: Optional[str] = None

    limit: Optional[int] = None

    filters: list[FilterSpec] = Field(default_factory=list)

    sort: Optional[SortSpec] = None

    group_by: Optional[list[str]] = Field(default_factory=list)

    time: Optional[TimeSpec] = None

    is_clarification_response: bool = False

    raw_utterance: Optional[str] = None
    confidence_score: float = 1.0

    @field_validator("group_by", mode="before")
    @classmethod
    def _normalize_group_by(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, (list, tuple)):
            return [str(x) for x in v if x]
        return []

    @field_validator("filters", mode="before")
    @classmethod
    def _normalize_filters(cls, v: Any) -> list[Any]:
        if v is None:
            return []
        return v

