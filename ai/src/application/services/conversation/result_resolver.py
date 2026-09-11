"""Result Resolver (spec section 9). Never calls NL2SQL."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from src.application.dto.conversation.conversation_llm_schemas import ResultResolutionOutput
from src.application.dto.llm.generation_request import GenerationRequest
from src.application.ports.llm_client import LLMClient
from src.prompts.result_resolution_prompt import RESULT_RESOLUTION_PROMPT

logger = logging.getLogger(__name__)

_NOT_FOUND_MESSAGE = (
    "The stored result from the previous query doesn't contain that information."
)


class ResultResolver:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def resolve(self, current_question: str, retrieved_context: dict[str, Any]) -> str:
        if not retrieved_context.get("execution_result_summary"):
            return _NOT_FOUND_MESSAGE

        prompt = RESULT_RESOLUTION_PROMPT.format(
            retrieved_context=retrieved_context,
            current_question=current_question,
        )
        try:
            response = self._llm_client.generate(
                GenerationRequest(prompt=prompt, response_model=ResultResolutionOutput)
            )
            result = ResultResolutionOutput.model_validate_json(response.text)
            if not result.found:
                return result.answer or _NOT_FOUND_MESSAGE
            return result.answer
        except (ValidationError, Exception) as exc:  # noqa: BLE001 - deliberate fail-safe
            logger.warning("Result resolution failed: %s", exc)
            return _NOT_FOUND_MESSAGE
