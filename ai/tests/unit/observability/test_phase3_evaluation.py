from src.observability.debug_runner import DebugResult
from src.observability.evaluation import EvaluationCase, comparison_matrix, evaluate, retrieval_evidence


def result(layer, *, local=None, tags=None, metrics=None, status="passed"):
    return DebugResult(layer, (), status, metrics or {}, tags or {"top_k": 8}, local or {})


def test_retrieval_ground_truth_metrics_are_evidence_based() -> None:
    run = result("retrieval", local={"retrieval": [{"payload": {"mapping": "Sales.Amount"}, "score": .9, "type": "dimension", "id": "sales"}, {"payload": {"mapping": "Region.Name"}}]})
    evidence = retrieval_evidence(EvaluationCase("x", "q", expected_tables=("Sales", "Region")), run)
    assert evidence["retrieval_hit_at_k"] is True and evidence["table_recall"] == 1.0
    assert evidence["results"][0]["rank"] == 1 and evidence["results"][0]["score"] == .9


def test_missing_ground_truth_is_not_evaluated() -> None:
    evidence = retrieval_evidence(EvaluationCase("x", "q"), result("retrieval", local={"retrieval": []}))
    assert evidence["evaluation_not_available"] is True
    assert evidence["retrieval_hit_at_k"] == "not_evaluated"


class Runner:
    def run(self, question, layer):
        if layer == "retrieval": return result(layer, local={"retrieval": [{"payload": {"mapping": "Sales.Amount"}}]})
        return result(layer, metrics={"request_latency_ms": 2, "validation_passed": 1}, tags={"prompt_hash": "hash", "model_identifier": "model", "semantic_revision": "rev"})


def test_dataset_evaluation_marks_unknown_categories_without_hallucination_label() -> None:
    report = evaluate([EvaluationCase("x", "q", expected_tables=("Sales",))], runner_factory=Runner)
    categories = report["cases"][0]["failure_analysis"]
    assert categories["schema_hallucination"] == "unknown"
    assert "hallucination_score" not in categories


def test_full_flow_marks_internal_stages_unavailable_instead_of_executed() -> None:
    report = evaluate([EvaluationCase("x", "q")], runner_factory=Runner)
    assert report["cases"][0]["failure_analysis"]["schema_hallucination"] == "unknown"


def test_comparison_flags_only_numeric_regressions() -> None:
    report_a = {"evaluation_run_id": "a", "metrics": {"validation_pass_rate": 1.0, "retrieval_hit_at_k_rate": 1.0}}
    report_b = {"evaluation_run_id": "b", "metrics": {"validation_pass_rate": .5, "retrieval_hit_at_k_rate": .5}}
    assert comparison_matrix([report_a, report_b])["rows"][1]["regression_vs_baseline"]["validation_pass_rate"] is True
