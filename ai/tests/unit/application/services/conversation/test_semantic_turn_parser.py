"""Unit tests for SemanticTurnParser."""
from datetime import datetime
import json
import pytest

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.ports.llm_client import LLMClient
from src.application.services.conversation.models.semantic_intent_contract import SemanticTurnIntent
from src.application.services.conversation.semantic_routing.application.semantic_turn_parser import (
    SemanticTurnParser,
)


class MockLLMClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.call_history: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_history.append(request)
        for pattern, resp_json in self.responses.items():
            if pattern.lower() in request.prompt.lower():
                return GenerationResponse(text=resp_json)
        # Default response
        return GenerationResponse(text=json.dumps({"action": "NEW_QUERY", "target_entity": "data"}))


def test_semantic_turn_parser_new_query():
    responses = {
        "show top 5 accounts": json.dumps({
            "action": "NEW_QUERY",
            "target_entity": "accounts",
            "limit": 5,
            "sort": {"target": "balance", "direction": "DESC"},
            "filters": [],
        })
    }
    parser = SemanticTurnParser(llm_client=MockLLMClient(responses))
    intent = parser.parse("Show top 5 accounts")
    assert intent.action == "NEW_QUERY"
    assert intent.target_entity == "accounts"
    assert intent.limit == 5
    assert intent.sort is not None
    assert intent.sort.direction == "DESC"


def test_semantic_equivalence_different_wordings():
    # Both "Give me the five largest accounts" and "What are the five biggest accounts"
    # produce equivalent semantic representations
    payload = json.dumps({
        "action": "NEW_QUERY",
        "target_entity": "accounts",
        "limit": 5,
        "sort": {"target": "balance", "direction": "DESC"},
    })
    responses = {
        "largest accounts": payload,
        "biggest accounts": payload,
    }
    parser = SemanticTurnParser(llm_client=MockLLMClient(responses))

    intent1 = parser.parse("Give me the five largest accounts")
    intent2 = parser.parse("What are the five biggest accounts?")

    assert intent1.action == intent2.action == "NEW_QUERY"
    assert intent1.limit == intent2.limit == 5
    assert intent1.sort.target == intent2.sort.target == "balance"


def test_semantic_turn_parser_modify_query_and_clarification():
    responses = {
        "inactive": json.dumps({
            "action": "CLARIFICATION_ANSWER",
            "filters": [{"target": "status", "operator": "eq", "value": "Inactive"}],
            "is_clarification_response": True,
        }),
        "what about cairo": json.dumps({
            "action": "MODIFY_QUERY",
            "filters": [{"target": "city", "operator": "eq", "value": "Cairo"}],
        }),
    }
    parser = SemanticTurnParser(llm_client=MockLLMClient(responses))

    intent_clarify = parser.parse("inactive", has_history=True)
    assert intent_clarify.action == "CLARIFICATION_ANSWER"
    assert intent_clarify.is_clarification_response is True
    assert intent_clarify.filters[0].value == "Inactive"

    intent_modify = parser.parse("What about Cairo?", has_history=True)
    assert intent_modify.action == "MODIFY_QUERY"
    assert intent_modify.filters[0].value == "Cairo"


def test_semantic_turn_parser_reset():
    responses = {
        "start over": json.dumps({
            "action": "RESET",
        })
    }
    parser = SemanticTurnParser(llm_client=MockLLMClient(responses))
    intent = parser.parse("start over")
    assert intent.action == "RESET"


def test_semantic_turn_parser_fallback_without_llm():
    # When no LLM is provided, specialist EntityRecognizer still works deterministically
    parser = SemanticTurnParser(llm_client=None)
    intent = parser.parse("Top 20 users", has_history=True)
    assert intent.action == "MODIFY_QUERY"
    assert intent.limit == 20

    intent_reset = parser.parse("start over and reset context")
    assert intent_reset.action == "RESET"
