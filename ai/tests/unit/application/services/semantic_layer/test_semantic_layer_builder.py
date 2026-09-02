"""Unit tests for the canonical FullRebuildBuilder."""

from unittest.mock import Mock
import json

from src.application.dto.llm.generation_response import GenerationResponse
from src.application.dto.semantic_layer.semantic_layer_build_input import (
    SemanticLayerBuildInput,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.services.semantic_layer.builders.full_build_builder import (
    FullRebuildBuilder,
)


class TestFullRebuildBuilder:
    """Tests for the canonical full-rebuild builder."""

    def test_build_generates_initial_draft(self):
        """Build should send the generated prompt to the LLM and return its response."""

        llm_client = Mock()

        expected_text = (
            '{"metadata": {"status": "initial_draft", '
            '"validated": false, "human_review_required": true}, '
            '"entities": [{"mapping": "customers"}]}'
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

        builder = FullRebuildBuilder(llm_client)

        result = builder.build(build_input)
        assert isinstance(result, SemanticLayerBuildResponse)
        assert result.semantic_layer["metadata"]["status"] == "initial_draft"
        assert len(result.semantic_layer["entities"]) >= 1
        assert result.semantic_layer["entities"][0]["mapping"] == "customers"
        llm_client.generate.assert_called_once()

        generation_request = llm_client.generate.call_args.args[0]

        assert "SCHEMA:" in generation_request.prompt
        assert "RELATIONSHIPS:" in generation_request.prompt
        assert "DOCUMENTATION:\nNot provided." in generation_request.prompt
        assert "BUSINESS GLOSSARY:\nNot provided." in generation_request.prompt
        assert "SAMPLE DATA:\nNot provided." in generation_request.prompt
