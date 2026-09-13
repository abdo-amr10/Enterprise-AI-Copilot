"""Structured Semantic Turn Parser.

Parses user utterances into structured SemanticTurnIntent contracts using the
configured local LLM and specialist EntityRecognizer for numbers and temporal expressions.
Decouples conversational language interpretation from physical SQL generation and schema authority.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.ports.llm_client import LLMClient
from src.application.services.conversation.extraction.entity_recognizer import EntityRecognizer
from src.application.services.conversation.models.semantic_intent_contract import (
    FilterSpec,
    SemanticTurnIntent,
    SortSpec,
    TimeSpec,
)
from src.application.services.conversation.normalization.normalizer import RequestNormalizer

logger = logging.getLogger(__name__)

_SEMANTIC_TURN_PROMPT = """You are an enterprise conversation semantic turn parser.
Your task is to interpret the user's natural language message and return a strictly structured semantic representation.

INSTRUCTIONS:
1. Interpret meaning, not surface words. Do not rely on exact keywords. Different linguistic expressions with the same meaning must produce equivalent structured meaning.
   Examples of equivalence:
   - "Show the top 5 accounts" == "Give me the five largest accounts" == "What are the five biggest accounts" == "Show me the 5 accounts with the highest balance" -> action: "NEW_QUERY", limit: 5, target_entity: "accounts", sort: {{"target": "balance", "direction": "DESC"}}
2. ACTIONS:
   - NEW_QUERY: An independent question or request starting a new topic.
   - MODIFY_QUERY: A follow-up modifying, filtering, sorting, or limiting the previous query.
   - CLARIFICATION_ANSWER: A concise response, single-word answer, or selection answering the assistant's previous clarification question.
   - RESET: Explicit request to start over, forget previous queries, or reset context.
3. DO NOT invent database schema fields or relationships.
4. DO NOT generate SQL.
5. DO NOT make security or authorization decisions.

CONTEXT:
Has previous query context: {has_context}
Recent dialogue:
{conversation_context}

USER MESSAGE:
"{message}"

OUTPUT FORMAT:
Return ONLY a valid JSON object adhering to this schema (no markdown fences, no extra text):
{{
  "action": "NEW_QUERY" | "MODIFY_QUERY" | "CLARIFICATION_ANSWER" | "RESET",
  "target_entity": "<entity or concept, e.g. customers, accounts, or null>",
  "limit": <integer or null>,
  "filters": [
    {{
      "target": "<attribute name, e.g. city, balance, status>",
      "operator": "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "like" | "in" | "between",
      "value": <extracted value>
    }}
  ],
  "sort": {{
    "target": "<attribute name or null>",
    "direction": "ASC" | "DESC"
  }} | null,
  "group_by": ["<attribute name>"],
  "time": {{
    "source_text": "<temporal expression>",
    "type": "date" | "datetime" | "date_range" | "duration" | "relative",
    "start": "<iso-date or null>",
    "end": "<iso-date or null>",
    "timex": "<timex or null>"
  }} | null,
  "is_clarification_response": false
}}
"""


class SemanticTurnParser:
    """Interprets user turns into structured SemanticTurnIntent using local LLM + EntityRecognizer."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        entity_recognizer: Optional[EntityRecognizer] = None,
    ) -> None:
        self._llm_client = llm_client
        self._entity_recognizer = entity_recognizer or EntityRecognizer()

    def parse(
        self,
        message: str,
        *,
        conversation_context: Optional[str] = None,
        has_history: bool = False,
        reference_datetime: Optional[datetime] = None,
    ) -> SemanticTurnIntent:
        """Parse natural language message into SemanticTurnIntent."""
        norm_msg = RequestNormalizer.normalize(message)
        if not norm_msg:
            return SemanticTurnIntent(
                action="NEW_QUERY",
                raw_utterance=message,
                confidence_score=0.0,
            )

        # 1. Check for LLM generation
        if self._llm_client is not None:
            try:
                prompt = _SEMANTIC_TURN_PROMPT.format(
                    has_context="Yes" if has_history else "No",
                    conversation_context=conversation_context.strip() if conversation_context else "None",
                    message=message.strip(),
                )
                gen_resp = self._llm_client.generate(GenerationRequest(prompt=prompt, format="json"))
                raw_text = (gen_resp.text or "").strip()
                parsed = self._deserialize_intent(raw_text, raw_utterance=message)
                if parsed:
                    # Normalize numbers & time via specialist EntityRecognizer
                    self._normalize_with_recognizer(parsed, message, reference_datetime)
                    return parsed
            except Exception as exc:
                logger.warning("SemanticTurnParser LLM call failed, falling back to specialist recognizer: %s", exc)

        # 2. Specialist Fallback: parse intent deterministically using EntityRecognizer
        return self._fallback_parse(message, has_history=has_history, reference_datetime=reference_datetime)

    def parse_turn(
        self,
        message: str,
        *,
        conversation_context: Optional[str] = None,
        has_history: bool = False,
        reference_datetime: Optional[datetime] = None,
    ) -> SemanticTurnIntent:
        """Alias for parse to support parse_turn interface."""
        return self.parse(
            message,
            conversation_context=conversation_context,
            has_history=has_history,
            reference_datetime=reference_datetime,
        )

    def _deserialize_intent(self, text: str, raw_utterance: str) -> Optional[SemanticTurnIntent]:
        """Safely parse JSON response into SemanticTurnIntent."""
        if not text:
            return None
        clean = text
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
            clean = re.sub(r"\s*```$", "", clean)
        clean = clean.strip()

        try:
            intent = SemanticTurnIntent.model_validate_json(clean)
            intent.raw_utterance = raw_utterance
            return intent
        except Exception as exc:
            logger.debug("Failed to validate SemanticTurnIntent JSON: %s (raw='%s')", exc, clean)
            # Try regex object match if surrounded by extra commentary
            match = re.search(r"\{.*\}", clean, re.DOTALL)
            if match:
                try:
                    intent = SemanticTurnIntent.model_validate_json(match.group(0))
                    intent.raw_utterance = raw_utterance
                    return intent
                except Exception:
                    pass
            return None

    def _normalize_with_recognizer(
        self,
        intent: SemanticTurnIntent,
        message: str,
        reference_datetime: Optional[datetime],
    ) -> None:
        """Augment LLM extracted intent with precision EntityRecognizer numbers and dates."""
        # Normalize limit if missing or 0
        if intent.limit is None or intent.limit <= 0:
            extracted_lim = self._entity_recognizer.extract_limit(message, default=0)
            if extracted_lim > 0:
                intent.limit = extracted_lim

        # Normalize temporal expression if time was missing
        if intent.time is None:
            time_spec = self._entity_recognizer.extract_first_datetime_range(
                message, reference_datetime=reference_datetime
            )
            if time_spec:
                intent.time = time_spec

    def _fallback_parse(
        self,
        message: str,
        has_history: bool,
        reference_datetime: Optional[datetime],
    ) -> SemanticTurnIntent:
        """Deterministic semantic fallback using EntityRecognizer when LLM is offline."""
        norm_msg = RequestNormalizer.normalize(message)
        numbers = self._entity_recognizer.extract_numbers(message)
        ordinals = self._entity_recognizer.extract_ordinals(message)
        time_spec = self._entity_recognizer.extract_first_datetime_range(message, reference_datetime)

        # Context reset check
        if any(norm_msg.startswith(p) for p in ("start over", "reset", "forget previous", "new question")):
            return SemanticTurnIntent(
                action="RESET",
                raw_utterance=message,
                confidence_score=0.95,
            )

        limit_val = None
        if numbers and ("top" in norm_msg or "limit" in norm_msg or "first" in norm_msg):
            limit_val = int(numbers[0].value)
        elif ordinals and ("top" in norm_msg or "first" in norm_msg):
            limit_val = int(ordinals[0].value)

        action = "MODIFY_QUERY" if has_history else "NEW_QUERY"

        return SemanticTurnIntent(
            action=action,
            limit=limit_val,
            time=time_spec,
            raw_utterance=message,
            confidence_score=0.75,
        )
