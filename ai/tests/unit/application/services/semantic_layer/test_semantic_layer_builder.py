"""Unit tests for the SemanticLayerBuilder application service."""

from unittest.mock import Mock
import json

from src.application.dto.llm.generation_response import GenerationResponse
from src.application.dto.semantic_layer.semantic_layer_build_input import (
    SemanticLayerBuildInput,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.services.semantic_layer.semantic_layer_builder import (
    SemanticLayerBuilder,
)


class TestSemanticLayerBuilder:
    """Tests for the SemanticLayerBuilder service."""

    def test_build_generates_initial_draft(self):
        """Build should send the generated prompt to the LLM and return its response."""

        llm_client = Mock()

        expected_text = (
            '{"metadata": {"status": "initial_draft", '
            '"validated": false, "human_review_required": true}}'
        )

        llm_client.generate.return_value = GenerationResponse(
            text=expected_text
        )

        build_input = SemanticLayerBuildInput(
            schema={
                "version": "1.0",
                "database": "Test Database",
                "tables": {
                    "customers": {
                        "columns": [
                            {
                                "name": "customer_id",
                                "type": "int",
                                "primary_key": True,
                            }
                        ]
                    }
                },
            },
            relationships=[],
            documentation=None,
            business_glossary=None,
            sample_data=None,
        )

        builder = SemanticLayerBuilder(llm_client)

        result = builder.build(build_input)
        expected_semantic_layer = json.loads(expected_text)

        assert isinstance(result, SemanticLayerBuildResponse)
        assert result.semantic_layer == expected_semantic_layer
        llm_client.generate.assert_called_once()

        generation_request = llm_client.generate.call_args.args[0]

        assert "schema:" in generation_request.prompt
        assert "relationships:" in generation_request.prompt
        assert "documentation:" in generation_request.prompt
        assert "business_glossary:" in generation_request.prompt
        assert "sample_data:" in generation_request.prompt
