import json
from typing import Any

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.dto.semantic_layer.semantic_layer_build_input import (
    SemanticLayerBuildInput,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.ports.llm_client import LLMClient
from src.infrastructure.semantic_layer.builders.semantic_layer_output_parser import (
    SemanticLayerOutputParser,
)
from src.prompts.full_build_prompt import (
    FULL_BUILD_PROMPT,
)


class FullRebuildBuilder:
    """Build a complete initial Semantic Layer from authoritative sources."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client
        self._output_parser = SemanticLayerOutputParser()

    def build(
        self,
        build_input: SemanticLayerBuildInput,
    ) -> SemanticLayerBuildResponse:
        """Generate the initial Semantic Layer draft."""

        prompt = self._build_prompt(build_input)

        response: GenerationResponse = self._llm_client.generate(
            GenerationRequest(prompt=prompt)
        )

        semantic_layer = self._output_parser.parse(response.text)

        return SemanticLayerBuildResponse(
            semantic_layer=semantic_layer,
        )

    @staticmethod
    def _build_prompt(
        build_input: SemanticLayerBuildInput,
    ) -> str:
        """Build the Full Rebuild LLM prompt."""

        documentation = (
            build_input.documentation
            if build_input.documentation is not None
            else "Not provided."
        )

        business_glossary = (
            build_input.business_glossary
            if build_input.business_glossary is not None
            else "Not provided."
        )

        sample_data = (
            json.dumps(
                build_input.sample_data,
                indent=2,
                ensure_ascii=False,
            )
            if build_input.sample_data is not None
            else "Not provided."
        )

        return f"""
{FULL_BUILD_PROMPT}

SCHEMA:
{json.dumps(build_input.schema, indent=2, ensure_ascii=False)}

RELATIONSHIPS:
{json.dumps(build_input.relationships, indent=2, ensure_ascii=False)}

DOCUMENTATION:
{documentation}

BUSINESS GLOSSARY:
{business_glossary}

SAMPLE DATA:
{sample_data}
""".strip()
