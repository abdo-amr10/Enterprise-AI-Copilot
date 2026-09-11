"""Conversation Layer test suite (spec Phase 6).

Covers the 10 required scenarios:
  1. Independent question
  2. Question follow-up
  3. SQL follow-up
  4. Result follow-up
  5. Multi-turn follow-up
  6. Ambiguous question
  7. Out-of-scope question
  8. Follow-up requiring previous SQL
  9. Follow-up requiring previous result
  10. Follow-up where only previous question is required

Each test builds the raw `conversation` tuple exactly as Backend would
send it (plain dicts, `role: "turn"` convention) -- no internal
ConversationTurn objects are constructed directly, so these tests also
exercise ConversationManager's parsing.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from src.application.services.conversation.context_resolver import ContextResolver
from src.application.services.conversation.conversation_layer import ConversationLayer
from src.application.services.conversation.conversation_manager import ConversationManager
from src.application.services.conversation.followup_analyzer import FollowupAnalyzer
from src.application.services.conversation.result_resolver import ResultResolver
from src.config.conversation_settings import ConversationSettings
from tests.unit.application.services.conversation.fake_llm_client import (
    FailingLLMClient,
    FakeSequentialLLMClient,
)


def _turn(turn_id, question, sql=None, result_summary=None):
    return {
        "role": "turn",
        "turn_id": turn_id,
        "user_question": question,
        "generated_sql": sql,
        "execution_result_summary": result_summary,
    }


def _build_layer(analyzer_response, resolver_response=None, result_response=None):
    analyzer_client = FakeSequentialLLMClient([analyzer_response])
    resolver_client = FakeSequentialLLMClient([resolver_response] if resolver_response else [])
    result_client = FakeSequentialLLMClient([result_response] if result_response else [])
    return ConversationLayer(
        conversation_manager=ConversationManager(ConversationSettings(context_window=5)),
        followup_analyzer=FollowupAnalyzer(analyzer_client),
        context_resolver=ContextResolver(resolver_client),
        result_resolver=ResultResolver(result_client),
    )


# 1. Independent question -- no prior turns at all.
def test_independent_question_with_no_history():
    layer = _build_layer(analyzer_response="{}")  # never called: short-circuited before LLM
    decision = layer.process("How many customers do we have?", ())
    assert decision.classification == "INDEPENDENT"
    assert decision.next_action == "NL2SQL"
    assert decision.resolved_question == "How many customers do we have?"


# 2. Question follow-up -- previous question only.
def test_question_follow_up_resolves_standalone_question():
    prev = _turn("turn_1", "How many orders did we have in 2025?")
    analyzer_json = json.dumps({
        "classification": "QUESTION_FOLLOW_UP",
        "confidence": 0.95,
        "context_requirement": "QUESTION_ONLY",
        "referenced_turn_id": "turn_1",
    })
    resolver_json = json.dumps({"resolved_question": "How many orders did we have in 2024?"})
    layer = _build_layer(analyzer_json, resolver_response=resolver_json)

    decision = layer.process("What about 2024?", (prev,))

    assert decision.classification == "QUESTION_FOLLOW_UP"
    assert decision.next_action == "NL2SQL"
    assert decision.context_requirement == "QUESTION_ONLY"
    assert decision.resolved_question == "How many orders did we have in 2024?"
    assert decision.retrieved_turn_ids == ("turn_1",)


# 3. SQL follow-up -- needs previous question + SQL.
def test_sql_follow_up_uses_previous_sql_context():
    prev = _turn("turn_2", "Show total sales by country.", sql="SELECT country, SUM(amount) FROM sales GROUP BY country;")
    analyzer_json = json.dumps({
        "classification": "SQL_FOLLOW_UP",
        "confidence": 0.9,
        "context_requirement": "QUESTION_AND_SQL",
        "referenced_turn_id": "turn_2",
    })
    resolver_json = json.dumps({"resolved_question": "Show total sales for Egypt."})
    layer = _build_layer(analyzer_json, resolver_response=resolver_json)

    decision = layer.process("Keep the same filters but only Egypt.", (prev,))

    assert decision.classification == "SQL_FOLLOW_UP"
    assert decision.context_requirement == "QUESTION_AND_SQL"
    assert decision.next_action == "NL2SQL"
    assert decision.resolved_question == "Show total sales for Egypt."


# 4. Result follow-up -- answered directly, no NL2SQL.
def test_result_follow_up_answers_directly_without_nl2sql():
    prev = _turn("turn_3", "Show total sales by country.", result_summary="Egypt: $2.5M, Brazil: $1.1M")
    analyzer_json = json.dumps({
        "classification": "RESULT_FOLLOW_UP",
        "confidence": 0.94,
        "context_requirement": "RESULT_ONLY",
        "referenced_turn_id": "turn_3",
    })
    result_json = json.dumps({"found": True, "answer": "Egypt's total sales were $2.5M."})
    layer = _build_layer(analyzer_json, result_response=result_json)

    decision = layer.process("What was the sales amount for Egypt?", (prev,))

    assert decision.classification == "RESULT_FOLLOW_UP"
    assert decision.next_action == "RESULT_RESOLVER"
    assert decision.direct_answer == "Egypt's total sales were $2.5M."
    assert decision.context_requirement == "RESULT_ONLY"


# 5. Multi-turn follow-up -- analyzer picks a specific earlier turn out of several.
def test_multi_turn_history_selects_the_referenced_turn():
    turns = (
        _turn("turn_1", "Show total sales by country.", sql="SELECT country, SUM(amount) FROM sales GROUP BY country;"),
        _turn("turn_2", "What about 2024?"),
        _turn("turn_3", "Show customer counts by branch."),
    )
    analyzer_json = json.dumps({
        "classification": "SQL_FOLLOW_UP",
        "confidence": 0.88,
        "context_requirement": "QUESTION_AND_SQL",
        "referenced_turn_id": "turn_1",
    })
    resolver_json = json.dumps({"resolved_question": "Show total sales by country for Egypt only."})
    layer = _build_layer(analyzer_json, resolver_response=resolver_json)

    decision = layer.process("Only Egypt, from the sales by country one.", turns)

    assert decision.retrieved_turn_ids == ("turn_1",)
    assert decision.resolved_question == "Show total sales by country for Egypt only."


# 6. Ambiguous question -- no guessing, ask for clarification.
def test_ambiguous_reference_requests_clarification():
    prev = _turn("turn_4", "Show sales by country.")
    analyzer_json = json.dumps({
        "classification": "AMBIGUOUS",
        "confidence": 0.4,
        "context_requirement": "NONE",
        "referenced_turn_id": None,
    })
    layer = _build_layer(analyzer_json)

    decision = layer.process("What about them?", (prev,))

    assert decision.classification == "AMBIGUOUS"
    assert decision.next_action == "CLARIFICATION"
    assert decision.clarification_message


# 7. Out-of-scope question -- rejected, no retrieval, no NL2SQL.
def test_out_of_scope_question_is_rejected_without_retrieval():
    prev = _turn("turn_5", "Show sales by country.")
    analyzer_json = json.dumps({
        "classification": "OUT_OF_SCOPE",
        "confidence": 0.99,
        "context_requirement": "NONE",
        "referenced_turn_id": None,
    })
    layer = _build_layer(analyzer_json)

    decision = layer.process("What's the weather today?", (prev,))

    assert decision.classification == "OUT_OF_SCOPE"
    assert decision.next_action == "REJECT"
    assert decision.retrieved_turn_ids == ()


# 8. Follow-up requiring previous SQL specifically (distinct from question-only).
def test_followup_requiring_sql_retrieves_sql_field():
    prev = _turn("turn_6", "Show total sales by country.", sql="SELECT country, SUM(amount) AS total FROM sales GROUP BY country;")
    analyzer_json = json.dumps({
        "classification": "SQL_FOLLOW_UP",
        "confidence": 0.9,
        "context_requirement": "QUESTION_AND_SQL",
        "referenced_turn_id": "turn_6",
    })
    resolver_json = json.dumps({"resolved_question": "Show total sales by country, sorted descending."})
    resolver_client_capture = FakeSequentialLLMClient([resolver_json])
    layer = ConversationLayer(
        conversation_manager=ConversationManager(ConversationSettings()),
        followup_analyzer=FollowupAnalyzer(FakeSequentialLLMClient([analyzer_json])),
        context_resolver=ContextResolver(resolver_client_capture),
        result_resolver=ResultResolver(FakeSequentialLLMClient([])),
    )

    layer.process("Sort that by total descending.", (prev,))

    # The resolver's prompt must have actually received the SQL, not just the question.
    assert "SELECT country, SUM(amount)" in resolver_client_capture.prompts[0]


# 9. Follow-up requiring previous result specifically.
def test_followup_requiring_result_only_does_not_leak_sql_into_prompt():
    prev = _turn(
        "turn_7", "Show total sales by country.",
        sql="SELECT country, SUM(amount) FROM sales GROUP BY country;",
        result_summary="Egypt: $2.5M, Brazil: $1.1M",
    )
    analyzer_json = json.dumps({
        "classification": "RESULT_FOLLOW_UP",
        "confidence": 0.93,
        "context_requirement": "RESULT_ONLY",
        "referenced_turn_id": "turn_7",
    })
    result_json = json.dumps({"found": True, "answer": "Egypt's total was $2.5M."})
    result_client_capture = FakeSequentialLLMClient([result_json])
    layer = ConversationLayer(
        conversation_manager=ConversationManager(ConversationSettings()),
        followup_analyzer=FollowupAnalyzer(FakeSequentialLLMClient([analyzer_json])),
        context_resolver=ContextResolver(FakeSequentialLLMClient([])),
        result_resolver=ResultResolver(result_client_capture),
    )

    decision = layer.process("What was Egypt's number?", (prev,))

    assert decision.direct_answer == "Egypt's total was $2.5M."
    # RESULT_ONLY must not have pulled the SQL into the resolver prompt.
    assert "SELECT country" not in result_client_capture.prompts[0]


# 10. Follow-up where only the previous question is required (no SQL, no result needed).
def test_followup_requiring_only_previous_question():
    prev = _turn("turn_8", "List active branches in Cairo.")
    analyzer_json = json.dumps({
        "classification": "QUESTION_FOLLOW_UP",
        "confidence": 0.92,
        "context_requirement": "QUESTION_ONLY",
        "referenced_turn_id": "turn_8",
    })
    resolver_json = json.dumps({"resolved_question": "List active branches in Alexandria."})
    layer = _build_layer(analyzer_json, resolver_response=resolver_json)

    decision = layer.process("What about Alexandria instead?", (prev,))

    assert decision.context_requirement == "QUESTION_ONLY"
    assert decision.resolved_question == "List active branches in Alexandria."


# Extra: fail-safe behavior when the LLM itself is unavailable.
def test_analyzer_llm_failure_defaults_to_ambiguous_not_a_crash():
    prev = _turn("turn_9", "Show sales by country.")
    layer = ConversationLayer(
        conversation_manager=ConversationManager(ConversationSettings()),
        followup_analyzer=FollowupAnalyzer(FailingLLMClient()),
        context_resolver=ContextResolver(FailingLLMClient()),
        result_resolver=ResultResolver(FailingLLMClient()),
    )

    decision = layer.process("What about that?", (prev,))

    assert decision.classification == "AMBIGUOUS"
    assert decision.next_action == "CLARIFICATION"


if __name__ == "__main__":
    import inspect
    module = sys.modules[__name__]
    for name, fn in inspect.getmembers(module, inspect.isfunction):
        if name.startswith("test_"):
            fn()
            print(f"PASSED: {name}")
    print("All Conversation Layer tests passed.")
