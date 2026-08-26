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
    report_a = {"evaluation_run_id": "a", "metrics": {"validation_pass_rate": 1.0, "retrieval_hit_at_k_rate": 1.0, "average_latency_ms": 100.0}}
    report_b = {"evaluation_run_id": "b", "metrics": {"validation_pass_rate": .5, "retrieval_hit_at_k_rate": .5, "average_latency_ms": 250.0}}
    matrix = comparison_matrix([report_a, report_b])
    assert matrix["rows"][1]["regression_vs_baseline"]["validation_pass_rate"] is True
    assert matrix["rows"][1]["regression_vs_baseline"]["average_latency_ms"] is True


def test_evaluation_and_comparison_matrix_computes_average_latency_honestly() -> None:
    class LatencyRunner:
        def __init__(self, latencies):
            self.latencies = latencies
        def run(self, question, layer):
            if layer == "retrieval":
                return result(layer, local={"retrieval": [{"payload": {"mapping": "Sales.Amount"}}]})
            return result(layer, metrics={"request_latency_ms": next(self.latencies), "validation_passed": 1}, tags={"prompt_hash": "h", "model_identifier": "m", "semantic_revision": "r"})

    cases = [EvaluationCase("1", "q1", expected_tables=("Sales",)), EvaluationCase("2", "q2", expected_tables=("Sales",))]
    latencies_a = iter([100.0, 200.0])
    report_a = evaluate(cases, runner_factory=lambda: LatencyRunner(latencies_a))
    assert report_a["metrics"]["average_latency_ms"] == 150.0

    latencies_b = iter([250.0, 350.0])
    report_b = evaluate(cases, runner_factory=lambda: LatencyRunner(latencies_b))
    assert report_b["metrics"]["average_latency_ms"] == 300.0

    matrix = comparison_matrix([report_a, report_b])
    assert matrix["rows"][0]["average_latency_ms"] == 150.0
    assert matrix["rows"][1]["average_latency_ms"] == 300.0
    assert matrix["rows"][1]["regression_vs_baseline"]["average_latency_ms"] is True



def test_missing_latency_remains_unavailable_without_inventing_zero() -> None:
    report_no_lat = {"evaluation_run_id": "none", "metrics": {"validation_pass_rate": 1.0}}
    matrix = comparison_matrix([report_no_lat])
    assert matrix["rows"][0]["average_latency_ms"] == "unavailable"
    assert "average_latency_ms" not in matrix["rows"][0]["regression_vs_baseline"]


def test_comparison_matrix_flags_configuration_differences_and_dataset_mismatch() -> None:
    report_a = {
        "evaluation_run_id": "run-a",
        "configuration": {"model_label": "model-1", "prompt_version_label": "v1"},
        "metrics": {"case_count": 10, "validation_pass_rate": 1.0},
    }
    report_b = {
        "evaluation_run_id": "run-b",
        "configuration": {"model_label": "model-2", "prompt_version_label": "v1"},
        "metrics": {"case_count": 10, "validation_pass_rate": 0.8},
    }
    report_c = {
        "evaluation_run_id": "run-c",
        "configuration": {"model_label": "model-1", "prompt_version_label": "v2"},
        "metrics": {"case_count": 5, "validation_pass_rate": 0.9},
    }

    matrix = comparison_matrix([report_a, report_b, report_c], baseline=0)

    # Candidate B vs Baseline A: model difference flagged, dataset compatible
    row_b = matrix["rows"][1]
    assert row_b["configuration_differences"] == {"model_label": {"baseline": "model-1", "candidate": "model-2"}}
    assert row_b["dataset_compatible"] is True

    # Candidate C vs Baseline A: prompt difference flagged, dataset count mismatch flagged
    row_c = matrix["rows"][2]
    assert row_c["configuration_differences"] == {"prompt_version_label": {"baseline": "v1", "candidate": "v2"}}
    assert row_c["dataset_compatible"] is False


