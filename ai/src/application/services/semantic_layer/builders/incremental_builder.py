import json
from typing import Any

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.ports.llm_client import LLMClient
from src.infrastructure.semantic_layer.builders.semantic_layer_output_parser import (
    SemanticLayerOutputParser,
)
from src.prompts.semantic_layer_incremental_prompt import (
    INCREMENTAL_PROMPT,
)


class IncrementalBuilder:
    """Build an incremental Semantic Layer revision."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client
        self._output_parser = SemanticLayerOutputParser()

    def build(
        self,
        base_semantic_layer: dict[str, Any],
        affected_objects: list[dict[str, Any]],
        updated_sources: dict[str, Any],
    ) -> SemanticLayerBuildResponse:
        """Generate an incremental Semantic Layer draft."""

        if not base_semantic_layer:
            raise ValueError(
                "base_semantic_layer cannot be empty."
            )

        if not affected_objects:
            raise ValueError(
                "affected_objects cannot be empty."
            )

        prompt = self._build_prompt(
            base_semantic_layer=base_semantic_layer,
            affected_objects=affected_objects,
            updated_sources=updated_sources,
        )

        response: GenerationResponse = self._llm_client.generate(
            GenerationRequest(prompt=prompt)
        )

        semantic_layer = self._output_parser.parse(response.text)

        return SemanticLayerBuildResponse(
            semantic_layer=semantic_layer,
        )

    @staticmethod
    def _build_prompt(
        base_semantic_layer: dict[str, Any],
        affected_objects: list[dict[str, Any]],
        updated_sources: dict[str, Any],
    ) -> str:
        """Build the Incremental LLM prompt."""

        return f"""
{INCREMENTAL_PROMPT}

BASE APPROVED SEMANTIC LAYER:
{json.dumps(
    base_semantic_layer,
    indent=2,
    ensure_ascii=False,
)}

AFFECTED OBJECTS:
{json.dumps(
    affected_objects,
    indent=2,
    ensure_ascii=False,
)}

UPDATED SOURCES:
{json.dumps(
    updated_sources,
    indent=2,
    ensure_ascii=False,
)}
""".strip()
