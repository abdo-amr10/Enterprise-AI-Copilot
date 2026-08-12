"""Application service for safely fixing semantic-layer validation issues."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.application.ports.llm_client import LLMClient
from src.application.dto.generation_request import GenerationRequest
from src.application.dto.generation_response import GenerationResponse
from src.application.prompts.semantic_layer.semantic_layer_auto_fixer_prompt import (
    SEMANTIC_LAYER_AUTO_FIXER_PROMPT,
)
from src.infrastructure.semantic_layer.builders.semantic_layer_output_parser import (
    SemanticLayerOutputParser,
)


class SemanticLayerAutoFixer:
    """Fix validation issues in an existing semantic-layer draft.

    The fixer does not rebuild the semantic layer from scratch.
    It only attempts to correct reported validation issues while
    preserving authoritative database metadata.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client
        self._output_parser = SemanticLayerOutputParser()

    def fix(
        self,
        draft: dict[str, Any],
        validation: dict[str, Any],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Attempt to fix the reported validation errors.

        Args:
            draft: Current semantic-layer draft.
            validation: Validation result for the current draft.
            schema: Authoritative database schema.

        Returns:
            Corrected semantic-layer draft.

        Raises:
            ValueError: If the LLM returns an invalid semantic layer.
        """

        errors = validation.get("errors", [])

        if not errors:
            return deepcopy(draft)

        prompt = self._build_prompt(
            draft=draft,
            validation=validation,
            schema=schema,
        )

        request = GenerationRequest(prompt=prompt)

        response: GenerationResponse = self._llm_client.generate(request)

        return self._output_parser.parse(response.text)

    @staticmethod
    def _build_prompt(
        draft: dict[str, Any],
        validation: dict[str, Any],
        schema: dict[str, Any],
    ) -> str:
        """Build the prompt used for safe validation correction."""

        import json

        return f"""
{SEMANTIC_LAYER_AUTO_FIXER_PROMPT}

CURRENT SEMANTIC LAYER:
{json.dumps(draft, indent=2, ensure_ascii=False)}

VALIDATION RESULT:
{json.dumps(validation, indent=2, ensure_ascii=False)}

AUTHORITATIVE DATABASE SCHEMA:
{json.dumps(schema, indent=2, ensure_ascii=False)}
""".strip()