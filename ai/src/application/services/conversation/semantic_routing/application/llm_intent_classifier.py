"""LLM-based Intent Classifier fallback for conversation routing."""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.ports.llm_client import LLMClient
from src.application.services.conversation.normalization.normalizer import (
    RequestNormalizer,
)
from src.application.services.conversation.semantic_routing.domain.classification_result import (
    IntentClassificationResult,
)
from src.application.services.conversation.semantic_routing.domain.intent import (
    ConversationIntent,
)

logger = logging.getLogger(__name__)

_INTENT_PROMPT_TEMPLATE = """You are an intent classifier for an enterprise database assistant.
Classify the user's message into exactly ONE of the following intents:

- LIMIT_CHANGE: User wants to limit, extract, or fetch top/first/last N results (e.g. "extract top 5", "pull the first 10", "limit to 3")
- SORT_CHANGE: User wants to reorder, sort, or rank results (e.g. "sort by date", "order by balance descending")
- GROUP_BY_CHANGE: User wants to group or aggregate results by an attribute (e.g. "group by department", "break down by region")
- FILTER_CHANGE: User wants to filter or narrow results or change a filter/scope (e.g. "only in Cairo", "what about laptops", "in 2024")
- CORRECTION: User corrects a previous query (e.g. "no, I meant 2025", "actually below 600")
- PRONOUN_REFERENCE: User refers to previous result items with pronouns (e.g. "which of them is highest?", "who among them works in sales?")
- RESET_CONTEXT: User explicitly wants to reset or start over (e.g. "start over", "new question", "reset")
- NEW_DATABASE_QUERY: A new, complete, independent database query (e.g. "show all orders", "how many employees are in HR?")
- OUT_OF_SCOPE: General conversation, greeting, joke, weather, or unrelated to data (e.g. "tell me a joke", "hello", "what is python?")
- AMBIGUOUS: Truly cannot be determined from available context (e.g. "what about it?", "that?")

Context:
Has previous query/result context: {has_history}

User message:
"{question}"

Respond with ONLY the exact intent name. Do not include explanation, punctuation, or markdown."""


class LLMIntentClassifier:
    """Classifies user conversational intent using a lightweight LLM call as fallback."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def classify(
        self,
        question: str,
        *,
        has_history: bool = False,
    ) -> IntentClassificationResult:
        """Classify user intent using the configured LLM."""
        norm_q = RequestNormalizer.normalize(question)
        if not norm_q:
            return IntentClassificationResult(
                intent=ConversationIntent.OUT_OF_SCOPE,
                confidence_score=0.0,
                margin=0.0,
                is_ambiguous=False,
                reason="Empty question provided.",
            )

        prompt = _INTENT_PROMPT_TEMPLATE.format(
            has_history="Yes" if has_history else "No",
            question=question.strip(),
        )

        try:
            gen_resp = self._llm_client.generate(GenerationRequest(prompt=prompt))
            raw_text = (gen_resp.text or "").strip()
            parsed_intent = self._parse_intent(raw_text)

            logger.info(
                "LLM intent classifier: question='%s' raw_response='%s' -> intent=%s",
                norm_q,
                raw_text,
                parsed_intent.value,
            )

            is_ambiguous = parsed_intent == ConversationIntent.AMBIGUOUS
            return IntentClassificationResult(
                intent=parsed_intent,
                confidence_score=0.85 if not is_ambiguous else 0.40,
                margin=0.10,
                is_ambiguous=is_ambiguous,
                reason=f"LLM fallback classification: {parsed_intent.value}",
            )
        except Exception as exc:
            logger.warning("LLM intent classifier failed: %s", exc)
            return IntentClassificationResult(
                intent=ConversationIntent.AMBIGUOUS,
                confidence_score=0.0,
                margin=0.0,
                is_ambiguous=True,
                reason=f"LLM intent classifier error: {exc}",
            )

    @staticmethod
    def _parse_intent(text: str) -> ConversationIntent:
        clean = re.sub(r"[^\w\s_]", " ", text).strip().upper()
        tokens = clean.split()

        # Check exact token match
        for token in tokens:
            for member in ConversationIntent:
                if token == member.value:
                    return member

        # Check substring match
        for member in ConversationIntent:
            if member.value in clean:
                return member

        return ConversationIntent.AMBIGUOUS
