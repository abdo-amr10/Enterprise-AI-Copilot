from src.application.dto.self_correction.critic_result import CriticResult
from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.application.dto.self_correction.validation_result import ValidationResult
from src.application.services.self_correction.self_correction_service import SelfCorrectionService


class _Context:
    def build_llm_context(self, question): return "context"


class _Validator:
    def __init__(self, invalid_sql=()): self.invalid_sql = set(invalid_sql); self.calls = []
    def validate(self, sql):
        self.calls.append(sql)
        return ValidationResult.fail([ValidationIssue("INVALID", "Invalid SQL", "test")]) if sql in self.invalid_sql else ValidationResult.ok()
    def schema_slice(self, sql): return {}
    def extract_tables(self, sql): return set()


class _Relationships:
    def validate(self, sql): return ValidationResult.ok()
    def relationships_for_tables(self, tables): return []


class _Critic:
    def __init__(self, statuses): self.statuses = iter(statuses); self.calls = []
    def evaluate(self, **kwargs): self.calls.append(kwargs["sql"]); return next(self.statuses)


class _Verifier:
    def verify(self, result):
        return [] if result.status == "PASS" else [ValidationIssue("INTENT", "Missing filter", "critic")]


class _Correction:
    def __init__(self, values): self.values = iter(values); self.calls = []
    def correct(self, **kwargs): self.calls.append(kwargs); return next(self.values)


def _service(syntax, critic, correction):
    return SelfCorrectionService(_Context(), syntax, _Validator(), _Relationships(), critic, _Verifier(), correction, max_attempts=3)


def test_valid_sql_always_enters_critic_and_passes_without_correction():
    critic = _Critic([CriticResult("PASS")])
    correction = _Correction([])
    outcome = _service(_Validator(), critic, correction).run("q", "SELECT 1", "context")
    assert outcome.is_valid and outcome.attempts_used == 0
    assert critic.calls == ["SELECT 1"] and correction.calls == []


def test_branch_scoped_sql_is_not_locally_rejected_for_backend_rls():
    critic = _Critic([CriticResult("PASS")])
    correction = _Correction([])
    outcome = _service(_Validator(), critic, correction).run(
        "Show customers in a branch",
        "SELECT c.customer_id FROM customers AS c",
        "context",
    )

    assert outcome.is_valid
    assert outcome.attempts_used == 0


def test_critic_failure_corrects_then_revalidates_and_recritiques():
    critic = _Critic([CriticResult("FAIL"), CriticResult("PASS")])
    correction = _Correction(["SELECT 2"])
    outcome = _service(_Validator(), critic, correction).run("q", "SELECT 1", "context")
    assert outcome.is_valid and outcome.sql == "SELECT 2" and outcome.attempts_used == 1
    assert critic.calls == ["SELECT 1", "SELECT 2"]


def test_loop_performs_at_most_three_actual_corrections():
    critic = _Critic([CriticResult("FAIL")] * 4)
    correction = _Correction(["SELECT 2", "SELECT 3", "SELECT 4"])
    outcome = _service(_Validator(), critic, correction).run("q", "SELECT 1", "context")
    assert not outcome.is_valid and outcome.attempts_used == 3
    assert len(correction.calls) == 3


def test_failed_first_correction_reports_one_actual_correction_attempt():
    critic = _Critic([CriticResult("FAIL")])
    correction = _Correction([None])
    outcome = _service(_Validator(), critic, correction).run("q", "SELECT 1", "context")
    assert not outcome.is_valid and outcome.attempts_used == 1


def test_trace_observer_reports_initial_attempt_correction_and_final_attempt():
    critic = _Critic([CriticResult("FAIL"), CriticResult("PASS")])
    correction = _Correction(["SELECT 2"])
    steps = []

    outcome = _service(_Validator(), critic, correction).run(
        "q", "SELECT 1", "context", trace_observer=steps.append
    )

    assert outcome.is_valid
    assert len(steps) == 3
    assert steps[0]["attempt"] == 0
    assert steps[0]["sql"] == "SELECT 1"
    assert steps[0]["criticStatus"] == "FAIL"
    assert steps[0]["verifiedCriticIssues"] == ["Missing filter"]
    assert steps[0]["action"] == "correction_required"

    assert steps[1] == {
        "event": "after_correction",
        "attempt": 1,
        "previousSql": "SELECT 1",
        "sql": "SELECT 2",
        "changed": True,
    }

    assert steps[2]["attempt"] == 1
    assert steps[2]["sql"] == "SELECT 2"
    assert steps[2]["criticStatus"] == "PASS"
    assert steps[2]["verifiedCriticIssues"] == []
    assert steps[2]["action"] == "passed"


def test_single_failure_passes_candidate_a_to_rejected_history():
    # TEST 1: A fails -> correction receives A in rejected history
    critic = _Critic([CriticResult("FAIL"), CriticResult("PASS")])
    correction = _Correction(["SELECT 2"])

    outcome = _service(_Validator(), critic, correction).run("q", "SELECT 1", "context")

    assert outcome.is_valid
    assert len(correction.calls) == 1
    first_call = correction.calls[0]
    assert first_call["current_sql"] == "SELECT 1"
    assert len(first_call["issues"]) == 1
    assert first_call["issues"][0].type == "INTENT"

    rejected = first_call["rejected_candidates"]
    assert len(rejected) == 1
    assert rejected[0][0] == "SELECT 1"
    assert rejected[0][1][0].type == "INTENT"


def test_multi_attempt_accumulates_rejected_history_with_isolated_active_issues():
    # TEST 2 & TEST 3:
    # A fails -> B fails -> correction for B receives both A and B in rejected_candidates,
    # but active issues contain ONLY B's current issues.
    critic = _Critic([CriticResult("FAIL"), CriticResult("FAIL"), CriticResult("PASS")])
    correction = _Correction(["SELECT 2", "SELECT 3"])

    outcome = _service(_Validator(), critic, correction).run("q", "SELECT 1", "context")

    assert outcome.is_valid
    assert len(correction.calls) == 2

    # Attempt 0 correction (fixing A)
    call_0 = correction.calls[0]
    assert call_0["current_sql"] == "SELECT 1"
    assert len(call_0["rejected_candidates"]) == 1
    assert call_0["rejected_candidates"][0][0] == "SELECT 1"

    # Attempt 1 correction (fixing B)
    call_1 = correction.calls[1]
    assert call_1["current_sql"] == "SELECT 2"
    # TEST 3: Active issues contain ONLY B's current issues (not accumulated A's issues)
    assert len(call_1["issues"]) == 1
    assert call_1["issues"][0].type == "INTENT"
    # TEST 2: Rejected history contains both A and B
    assert len(call_1["rejected_candidates"]) == 2
    assert call_1["rejected_candidates"][0][0] == "SELECT 1"
    assert call_1["rejected_candidates"][1][0] == "SELECT 2"


def test_seen_fingerprints_oscillation_terminates_cycle():
    # TEST 4 & TEST 5:
    # If the model returns A again (A -> B -> A), seen_fingerprints terminates the loop.
    critic = _Critic([CriticResult("FAIL"), CriticResult("FAIL")])
    # Correction returns SELECT 2, then returns SELECT 1 again (oscillation)
    correction = _Correction(["SELECT 2", "SELECT 1"])

    outcome = _service(_Validator(), critic, correction).run("q", "SELECT 1", "context")

    assert not outcome.is_valid
    assert any("CORRECTION_OSCILLATION" in iss for iss in outcome.issues)


def test_sql_correction_service_renders_rejected_candidates_in_prompt():
    # TEST 6 & Rendering check:
    # Verify that SQLCorrectionService formats the prompt with <REJECTED_CANDIDATES>
    from src.application.dto.llm.generation_request import GenerationRequest
    from src.application.dto.llm.generation_response import GenerationResponse
    from src.application.services.self_correction.sql_correction_service import SQLCorrectionService

    class _MockLLM:
        def __init__(self):
            self.requests = []
        def generate(self, request: GenerationRequest) -> GenerationResponse:
            self.requests.append(request)
            return GenerationResponse(text="SELECT 1")

    llm = _MockLLM()
    svc = SQLCorrectionService(llm)

    rejected = [
        ("SELECT * FROM customers", [ValidationIssue("RLS_MISSING", "Missing branch parameter", "rls")]),
        ("SELECT * FROM branches", [ValidationIssue("WRONG_TABLE", "Wrong table used", "schema")]),
    ]

    result = svc.correct(
        question="Show all customers",
        current_sql="SELECT * FROM branches",
        issues=[ValidationIssue("WRONG_TABLE", "Wrong table used", "schema")],
        relevant_schema={"customers": {"columns": [{"name": "customer_id"}]}},
        relevant_relationships=[],
        rejected_candidates=rejected,
    )

    assert result == "SELECT 1"
    assert len(llm.requests) == 1
    prompt_text = llm.requests[0].prompt

    assert "<REJECTED_CANDIDATES>" in prompt_text
    assert "Candidate #1:" in prompt_text
    assert "SELECT * FROM customers" in prompt_text
    assert "[RLS_MISSING] Missing branch parameter" in prompt_text
    assert "Candidate #2:" in prompt_text
    assert "SELECT * FROM branches" in prompt_text
    assert "[WRONG_TABLE] Wrong table used" in prompt_text


def test_sql_correction_service_backward_compatible_when_rejected_candidates_is_none():
    # TEST 7:
    # Backward compatibility when rejected_candidates is omitted or None
    from src.application.dto.llm.generation_request import GenerationRequest
    from src.application.dto.llm.generation_response import GenerationResponse
    from src.application.services.self_correction.sql_correction_service import SQLCorrectionService

    class _MockLLM:
        def __init__(self):
            self.requests = []
        def generate(self, request: GenerationRequest) -> GenerationResponse:
            self.requests.append(request)
            return GenerationResponse(text="SELECT 1")

    llm = _MockLLM()
    svc = SQLCorrectionService(llm)

    result = svc.correct(
        question="Show 1",
        current_sql="SELECT 0",
        issues=[ValidationIssue("INTENT", "Should be 1", "critic")],
        relevant_schema={},
        relevant_relationships=[],
    )

    assert result == "SELECT 1"
    prompt_text = llm.requests[0].prompt
    assert "<REJECTED_CANDIDATES>" in prompt_text
    assert "(no previous candidates rejected in this run)" in prompt_text
