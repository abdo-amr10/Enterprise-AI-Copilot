from unittest.mock import Mock
import pytest

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.infrastructure.llm.model_config import ModelConfig
from src.infrastructure.llm.ollama_client import OllamaClient, _parse_keep_alive


config = ModelConfig(
        model_name="qwen2.5-coder:7b",
        runtime="ollama",
        temperature=0.0,
        context_length=32768,
        max_output_tokens=2048,
    )


"""
Unit tests for OllamaClient.

These tests verify the client's behavior without connecting
to a real Ollama runtime by mocking the external Ollama client.
"""

def test_generate_returns_generation_response():
   """Verify that generate returns a GenerationResponse with the expected text."""
   
   client = OllamaClient(config)
   client._client = Mock()
   client._client.generate.return_value = {
      "response" : "SELECT * FROM customers;"
   }

   request = GenerationRequest(prompt="Get all customers.")

   result = client.generate(request)

   assert isinstance(result,GenerationResponse)
   assert result.text == "SELECT * FROM customers;"

def test_generate_sends_correct_configuration_to_ollama():
    """Verify that the correct model and generation settings are sent to Ollama.""" 

    client = OllamaClient(config)

    client._client = Mock()
    client._client.generate.return_value = {
        "response": "SELECT 1;"
    }

    request = GenerationRequest(
        prompt="Generate SQL."
    )

    client.generate(request)

    client._client.generate.assert_called_once_with(
        model="qwen2.5-coder:7b",
        prompt="Generate SQL.",
        options={
            "temperature": 0.0,
            "num_ctx": 32768,
            "num_predict": 2048,
        },
        keep_alive=-1,
    )


def test_generate_sends_format_to_ollama_when_specified():
    """Verify that format='json' is forwarded to Ollama when specified on the request."""

    client = OllamaClient(config)

    client._client = Mock()
    client._client.generate.return_value = {
        "response": '{"result": "ok"}'
    }

    request = GenerationRequest(
        prompt="Generate JSON.",
        format="json",
    )

    client.generate(request)

    client._client.generate.assert_called_once_with(
        model="qwen2.5-coder:7b",
        prompt="Generate JSON.",
        options={
            "temperature": 0.0,
            "num_ctx": 32768,
            "num_predict": 2048,
        },
        keep_alive=-1,
        format="json",
    )


def test_ollama_client_rejects_non_ollama_runtime():
    """Verify that OllamaClient rejects configurations using a non-Ollama runtime."""
    
    config = ModelConfig(
        model_name="some-model",
        runtime="vllm",
        temperature=0.0,
        context_length=32768,
        max_output_tokens=2048,
    )

    with pytest.raises(
        ValueError,
        match="OllamaClient requires an Ollama runtime",
    ):
        OllamaClient(config)


def test_parse_keep_alive_handles_integers_and_duration_strings():
    """Verify that _parse_keep_alive correctly converts strings without units into ints."""
    assert _parse_keep_alive("-1") == -1
    assert _parse_keep_alive("0") == 0
    assert _parse_keep_alive("300") == 300
    assert _parse_keep_alive(" 60 ") == 60
    assert _parse_keep_alive("5m") == "5m"
    assert _parse_keep_alive("24h") == "24h"
    assert _parse_keep_alive("") == -1
    assert _parse_keep_alive(None) == -1

   
