from typing import Any

from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)
from src.application.dto.semantic_layer.semantic_layer_build_input import (
    SemanticLayerBuildInput,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.services.semantic_layer.builders.full_build_builder import (
    FullRebuildBuilder,
)


class FullRebuildStrategy:
    """Build a complete Semantic Layer from authoritative sources.

    Previously this returned a stub dict (`{"triggerType": ...,
    "sources": ...}`) and never called an LLM at all. It now assembles
    a SemanticLayerBuildInput from `sources` and delegates to
    FullRebuildBuilder, which is the component that actually talks to
    the LLM.
    """

    def __init__(self, builder: FullRebuildBuilder) -> None:
        self._builder = builder

    def build(
        self,
        request: SemanticLayerGenerationRequest,
        sources: dict[str, Any],
        base_semantic_layer: dict[str, Any] | None = None,
    ) -> SemanticLayerBuildResponse:

        if request.trigger_type != "FullRebuild":
            raise ValueError(
                "FullRebuildStrategy requires trigger_type='FullRebuild'."
            )

        build_input = SemanticLayerBuildInput(
            schema=sources["schema"],
            relationships=sources["relationships"],
            documentation=sources.get("documentation"),
            business_glossary=sources.get("business_glossary"),
            sample_data=sources.get("sample_data"),
        )

        return self._builder.build(build_input)
