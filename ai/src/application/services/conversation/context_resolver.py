"""Context Resolver (spec section 8). Never generates SQL."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from src.application.dto.conversation.conversation_llm_schemas import ResolvedQuestionResult
from src.application.dto.llm.generation_request import GenerationRequest
from src.application.ports.llm_client import LLMClient
from src.prompts.context_resolution_prompt import CONTEXT_RESOLUTION_PROMPT

logger = logging.getLogger(__name__)


class ContextResolver:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def resolve(self, current_question: str, retrieved_context: dict[str, Any]) -> str:
        prompt = CONTEXT_RESOLUTION_PROMPT.format(
            retrieved_context=retrieved_context,
            current_question=current_question,
        )
        try:
            response = self._llm_client.generate(
                GenerationRequest(prompt=prompt, response_model=ResolvedQuestionResult)
            )
            result = ResolvedQuestionResult.model_validate_json(response.text)
            return result.resolved_question.strip() or current_question
        except (ValidationError, Exception) as exc:  # noqa: BLE001 - deliberate fail-safe
            logger.warning("Context resolution failed, falling back to the raw question: %s", exc)
            # Fail-safe: worst case, NL2SQL receives the unresolved question
            # instead of a crash. It may fail its own validation, which is
            # safer than fabricating a resolved question.
            return current_question
