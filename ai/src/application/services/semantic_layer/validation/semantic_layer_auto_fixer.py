"""Application service for safely fixing Semantic Layer validation issues."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.ports.llm_client import LLMClient
from src.infrastructure.semantic_layer.builders.semantic_layer_output_parser import (
    SemanticLayerOutputParser,
)
from src.prompts.semantic_layer_auto_fixer_prompt import (
    SEMANTIC_LAYER_AUTO_FIXER_PROMPT,
)


class SemanticLayerAutoFixer:
    """Fix validation errors without rebuilding the Semantic Layer."""

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize the auto-fixer."""

        self._llm_client = llm_client
        self._output_parser = SemanticLayerOutputParser()

    def fix(
        self,
        draft: dict[str, Any],
        validation: dict[str, Any],
        schema: dict[str, Any],
        relationships: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Attempt to correct validation errors.

        The fixer preserves the current Semantic Layer identity and
        semantic-object IDs.

        Args:
            draft: Current Semantic Layer draft.
            validation: Validation result.
            schema: Authoritative database schema.

        Returns:
            Corrected Semantic Layer draft.
        """

        errors = validation.get("errors", [])

        if not errors:
            return deepcopy(draft)

        prompt = self._build_prompt(
            draft=draft,
            validation=validation,
            schema=schema,
            relationships=relationships,
        )

        request = GenerationRequest(prompt=prompt)

        response: GenerationResponse = self._llm_client.generate(
            request
        )

        fixed_draft = self._output_parser.parse(response.text)

        return self._preserve_identity(
            original=draft,
            corrected=fixed_draft,
        )

    @staticmethod
    def _build_prompt(
        draft: dict[str, Any],
        validation: dict[str, Any],
        schema: dict[str, Any],
        relationships: list[dict[str, Any]],
    ) -> str:
        """Build the auto-fixer prompt."""

        return f"""
        {SEMANTIC_LAYER_AUTO_FIXER_PROMPT}

        IMPORTANT IDENTITY RULES:

        The following fields are authoritative and MUST NOT be changed:

        - semantic_layer_id
        - revision_id
        - base_revision_id
        - trigger_type

        The auto-fixer may correct semantic content only.
        It must preserve the Semantic Layer revision identity.

        CURRENT SEMANTIC LAYER:
        {json.dumps(draft, indent=2, ensure_ascii=False)}

        VALIDATION RESULT:
        {json.dumps(validation, indent=2, ensure_ascii=False)}

        AUTHORITATIVE DATABASE SCHEMA:
        {json.dumps(schema, indent=2, ensure_ascii=False)}

        AUTHORITATIVE DATABASE RELATIONSHIPS:
        {json.dumps(relationships, indent=2, ensure_ascii=False)}
        """.strip()

    @staticmethod
    def _preserve_identity(
        original: dict[str, Any],
        corrected: dict[str, Any],
    ) -> dict[str, Any]:
        """Preserve Semantic Layer and object identities.

        base_revision_id is now included alongside semantic_layer_id
        and revision_id. Previously it was told to the LLM as
        authoritative in the prompt but never actually enforced here
        -- if the LLM ignored the instruction, base_revision_id could
        silently drift or disappear, breaking Incremental lineage.
        """

        result = deepcopy(corrected)

        original_metadata = original.get("metadata", {})
        corrected_metadata = result.setdefault("metadata", {})

        for field in (
            "semantic_layer_id",
            "revision_id",
            "base_revision_id",
            "trigger_type",
        ):
            if field in original_metadata:
                corrected_metadata[field] = original_metadata[field]

        sections = (
            "entities",
            "relationships",
            "measures",
            "dimensions",
            "business_rules",
        )

        for section in sections:
            original_items = {
                item.get("name"): item
                for item in original.get(section, [])
                if isinstance(item, dict)
                and item.get("name")
            }

            for item in result.get(section, []):
                if not isinstance(item, dict):
                    continue

                name = item.get("name")
                original_item = original_items.get(name)

                if original_item and original_item.get("object_id"):
                    item["object_id"] = original_item["object_id"]

        return result
