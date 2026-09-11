"""Scope guard evaluating enterprise data domain scope before Text-to-SQL."""

from __future__ import annotations

from dataclasses import dataclass
import re

from src.application.services.conversation.normalization.normalizer import RequestNormalizer

_OUT_OF_SCOPE_MESSAGE = (
    "I can only help with questions about your data -- new queries, "
    "follow-ups on a previous query, or questions about a previous result."
)


@dataclass(frozen=True)
class ScopeEvaluation:
    is_in_scope: bool
    rejection_message: str | None = None
    reason: str | None = None


class ScopeGuard:
    """Evaluates whether a request falls within the enterprise data domain.

    Guards against general-purpose chatbot usage before expensive retrieval,
    LLM, or Text-to-SQL execution.
    """

    _CREATIVE_PATTERNS = re.compile(
        r"\b(?:write\s+(?:a\s+)?(?:poem|story|song|essay|joke|code\s+for)|tell\s+me\s+a\s+joke|compose\s+(?:a\s+)?(?:poem|song))\b",
        re.IGNORECASE,
    )

    _GENERAL_KNOWLEDGE_PATTERNS = re.compile(
        r"\b(?:what\s+is\s+the\s+capital\s+of|"
        r"who\s+(?:is|was)\s+(?:the\s+)?(?:president|king|queen|prime\s+minister)\s+of|"
        r"how\s+tall\s+is|who\s+won\s+the\s+world\s+cup|distance\s+to\s+the\s+moon)\b",
        re.IGNORECASE,
    )

    _CHITCHAT_PATTERNS = re.compile(
        r"\b(?:what\s+do\s+you\s+think\s+about\s+politics|"
        r"how\s+are\s+you(?:\s+doing)?|"
        r"what\s+is\s+the\s+meaning\s+of\s+life|"
        r"are\s+you\s+(?:sentient|alive|conscious|human)|"
        r"do\s+you\s+(?:love|hate|like)\s+(?:me|humans))\b",
        re.IGNORECASE,
    )

    _WEATHER_PATTERNS = re.compile(
        r"\b(?:what(?:\'s|\s+is)\s+the\s+weather|"
        r"will\s+it\s+rain|weather\s+in|temperature\s+in|"
        r"what\s+time\s+is\s+it\s+in)\b",
        re.IGNORECASE,
    )

    @classmethod
    def evaluate(cls, question: str) -> ScopeEvaluation:
        """Evaluate if the question is in scope for the enterprise data copilot."""
        norm_q = RequestNormalizer.normalize(question)

        if not norm_q:
            return ScopeEvaluation(
                is_in_scope=False,
                rejection_message=_OUT_OF_SCOPE_MESSAGE,
                reason="Empty query.",
            )

        if cls._CREATIVE_PATTERNS.search(norm_q):
            return ScopeEvaluation(
                is_in_scope=False,
                rejection_message=_OUT_OF_SCOPE_MESSAGE,
                reason="Creative request rejected.",
            )

        if cls._GENERAL_KNOWLEDGE_PATTERNS.search(norm_q):
            return ScopeEvaluation(
                is_in_scope=False,
                rejection_message=_OUT_OF_SCOPE_MESSAGE,
                reason="General knowledge trivia rejected.",
            )

        if cls._CHITCHAT_PATTERNS.search(norm_q):
            return ScopeEvaluation(
                is_in_scope=False,
                rejection_message=_OUT_OF_SCOPE_MESSAGE,
                reason="Chit-chat / opinion request rejected.",
            )

        if cls._WEATHER_PATTERNS.search(norm_q):
            return ScopeEvaluation(
                is_in_scope=False,
                rejection_message=_OUT_OF_SCOPE_MESSAGE,
                reason="External weather/time request rejected.",
            )

        return ScopeEvaluation(is_in_scope=True)
