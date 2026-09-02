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
from src.application.services.semantic_layer.relationships.relationship_service import (
    RelationshipProcessingEngine,
)


class FullRebuildStrategy:
    """Build a complete Semantic Layer from authoritative sources.

    Processes schema and relationships through the RelationshipProcessingEngine
    to validate, deduplicate, score, discover candidates, build the relationship
    graph, and detect disconnected components before delegating to FullRebuildBuilder.
    """

    def __init__(
        self,
        builder: FullRebuildBuilder,
        relationship_engine: RelationshipProcessingEngine | None = None,
    ) -> None:
        self._builder = builder
        self._relationship_engine = relationship_engine or RelationshipProcessingEngine()

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

        # Process through the Relationship Engine
        processing_result = self._relationship_engine.process(
            raw_schema=sources["schema"],
            explicit_relationships=sources.get("relationships"),
            sample_data=sources.get("sample_data"),
        )

        documentation = (
            sources.get("documentation")
            or sources.get("Documentation")
            or sources.get("docs")
            or sources.get("Docs")
        )
        business_glossary = (
            sources.get("business_glossary")
            or sources.get("businessGlossary")
            or sources.get("glossary")
            or sources.get("Glossary")
        )
        sample_data = (
            sources.get("sample_data")
            or sources.get("sampleData")
            or sources.get("SampleData")
        )

        build_input = SemanticLayerBuildInput(
            schema=sources["schema"],
            relationships=processing_result.to_semantic_layer_relationships(),
            documentation=documentation,
            business_glossary=business_glossary,
            sample_data=sample_data,
            relationship_graph=processing_result.graph.to_graph_dict(),
            disconnected_entities=processing_result.disconnected_analysis.disconnected_entities,
            relationship_registry=processing_result.registry.to_dict(),
        )

        return self._builder.build(build_input)

