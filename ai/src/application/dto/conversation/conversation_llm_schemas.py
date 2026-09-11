"""Structured-output schema for the Follow-up Analyzer LLM call."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class FollowupAnalysisResult(BaseModel):
    classification: Literal[
        "INDEPENDENT",
        "QUESTION_FOLLOW_UP",
        "SQL_FOLLOW_UP",
        "RESULT_FOLLOW_UP",
        "AMBIGUOUS",
        "OUT_OF_SCOPE",
    ]
    confidence: float
    context_requirement: Literal[
        "NONE",
        "QUESTION_ONLY",
        "QUESTION_AND_SQL",
        "RESULT_ONLY",
        "QUESTION_AND_RESULT",
        "QUESTION_SQL_AND_RESULT",
    ]
    referenced_turn_id: Optional[str] = None


class ResolvedQuestionResult(BaseModel):
    resolved_question: str


class ResultResolutionOutput(BaseModel):
    found: bool
    answer: str
