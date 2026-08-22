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
