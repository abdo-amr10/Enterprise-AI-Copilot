"""Unit tests for SemanticLayerOutputParser covering all parsing scenarios."""

import pytest
from src.infrastructure.semantic_layer.builders.semantic_layer_output_parser import (
    SemanticLayerOutputParser,
)


def test_parse_raw_json():
    parser = SemanticLayerOutputParser()
    raw = '{"semantic_layer_id": "layer-1", "entities": [{"name": "customers"}]}'
    result = parser.parse(raw)
    assert result["semantic_layer_id"] == "layer-1"
    assert len(result["entities"]) == 1


def test_parse_fenced_json():
    parser = SemanticLayerOutputParser()
    fenced = """```json
    {
      "semantic_layer_id": "layer-2",
      "version": "1.0"
    }
    ```"""
    result = parser.parse(fenced)
    assert result["semantic_layer_id"] == "layer-2"


def test_parse_prefixed_json():
    parser = SemanticLayerOutputParser()
    prefixed = """Here is the generated semantic layer:
    ```json
    {
      "semantic_layer_id": "layer-3",
      "status": "Ready"
    }
    ```"""
    result = parser.parse(prefixed)
    assert result["semantic_layer_id"] == "layer-3"


def test_parse_suffixed_json():
    parser = SemanticLayerOutputParser()
    suffixed = """```json
    {
      "semantic_layer_id": "layer-4"
    }
    ```
    Hope this helps your semantic layer modeling!"""
    result = parser.parse(suffixed)
    assert result["semantic_layer_id"] == "layer-4"


def test_parse_embedded_unfenced_json():
    parser = SemanticLayerOutputParser()
    embedded = """Note: The schema is below:
    {"semantic_layer_id": "layer-5", "count": 42}
    Please review it carefully."""
    result = parser.parse(embedded)
    assert result["semantic_layer_id"] == "layer-5"
    assert result["count"] == 42


def test_parse_nested_json():
    parser = SemanticLayerOutputParser()
    nested = """{
      "semantic_layer_id": "layer-6",
      "metadata": {
        "tags": ["prod", "finance"],
        "nested": {"deep": true}
      }
    }"""
    result = parser.parse(nested)
    assert result["metadata"]["nested"]["deep"] is True


def test_parse_empty_response_raises():
    parser = SemanticLayerOutputParser()
    with pytest.raises(ValueError, match="cannot be empty"):
        parser.parse("")

    with pytest.raises(ValueError, match="cannot be empty"):
        parser.parse("   \n\t  ")


def test_parse_malformed_json_raises():
    parser = SemanticLayerOutputParser()
    with pytest.raises(ValueError, match="not valid JSON"):
        parser.parse("This is just plain text with no json inside.")


def test_parse_json_array_raises():
    parser = SemanticLayerOutputParser()
    with pytest.raises(ValueError, match="must be a JSON object"):
        parser.parse("[1, 2, 3]")


def test_parse_json_with_trailing_commas():
    parser = SemanticLayerOutputParser()
    text = '{"semantic_layer_id": "layer-7", "entities": [{"name": "users", }, ], "count": 10, }'
    result = parser.parse(text)
    assert result["semantic_layer_id"] == "layer-7"
    assert result["entities"][0]["name"] == "users"
    assert result["count"] == 10


def test_parse_json_with_comments():
    parser = SemanticLayerOutputParser()
    text = """// Top level comment
    {
      /* Multi-line
         comment */
      "semantic_layer_id": "layer-8",
      "url": "http://example.com/api" // inline comment
    }"""
    result = parser.parse(text)
    assert result["semantic_layer_id"] == "layer-8"
    assert result["url"] == "http://example.com/api"


def test_parse_json_with_python_literals():
    parser = SemanticLayerOutputParser()
    text = '{"semantic_layer_id": "layer-9", "is_active": True, "archived": False, "details": None}'
    result = parser.parse(text)
    assert result["semantic_layer_id"] == "layer-9"
    assert result["is_active"] is True
    assert result["archived"] is False
    assert result["details"] is None


def test_parse_json_with_single_quotes():
    parser = SemanticLayerOutputParser()
    text = "{'semantic_layer_id': 'layer-10', 'entities': [{'name': 'orders'}]}"
    result = parser.parse(text)
    assert result["semantic_layer_id"] == "layer-10"
    assert result["entities"][0]["name"] == "orders"


def test_parse_truncated_json_recovery():
    parser = SemanticLayerOutputParser()
    text = '{"metadata": {"status": "initial_draft"}, "entities": [{"name": "customers"'
    result = parser.parse(text)
    assert result["metadata"]["status"] == "initial_draft"
    assert result["entities"][0]["name"] == "customers"

