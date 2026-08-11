import pytest

from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)

class TestSemanticLayerBuildResponse:
    """Tests for the SemanticLayerBuildResponse DTO."""

    def test_accepts_semantic_layer_dictionary(self):
        """Accept a dictionary representing an initial semantic-layer draft."""
        semantic_layer = {
            "metadata": {
                "status": "initial_draft",
                "validated": False,
                "human_review_required": True,
            },
            "entities": [],
            "relationships": [],
            "measures": [],
            "dimensions": [],
            "business_rules": [],
            "validation_issues": [],
        }

        response = SemanticLayerBuildResponse(
            semantic_layer=semantic_layer
        )

        assert response.semantic_layer == semantic_layer

    def test_rejects_non_dictionary_semantic_layer(self):
        """Reject invalid semantic-layer output types."""
        with pytest.raises(ValueError, match="semantic_layer must be a dictionary"):
            SemanticLayerBuildResponse(semantic_layer="invalid")