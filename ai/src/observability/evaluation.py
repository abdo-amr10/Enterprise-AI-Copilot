"""Evidence-based developer evaluation; it neither executes SQL nor judges with an LLM."""
from __future__ import annotations
import json, statistics, uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from src.observability.debug_runner import DebugResult, DebugRunner
from src.observability.mlflow_observer import MLflowObserver
from src.prompts.text_to_sql_prompt import TEXT_TO_SQL_PROMPT

UNKNOWN, NOT_EVALUATED, UNAVAILABLE = "unknown", "not_evaluated", "unavailable"

@dataclass(frozen=True)
class EvaluationCase:
    case_id: str; question: str; expected_sql: str | None = None
    expected_tables: tuple[str, ...] = (); expected_columns: tuple[str, ...] = ()
    expected_semantic_intent: str | None = None; tags: tuple[str, ...] = ()
    @property
    def retrieval_ground_truth_available(self) -> bool: return bool(self.expected_tables)

def load_dataset(path: str | Path) -> list[EvaluationCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8")); values = raw.get("cases", raw) if isinstance(raw, dict) else raw
    if not isinstance(values, list): raise ValueError("Dataset must be a JSON list or {'cases': [...]}.")
    cases=[]
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str) or not isinstance(item.get("question"), str): raise ValueError("Each case needs string case_id and question.")
        cases.append(EvaluationCase(case_id=item["case_id"], question=item["question"], expected_sql=item.get("expected_sql"), expected_tables=tuple(item.get("expected_tables", ())), expected_columns=tuple(item.get("expected_columns", ())), expected_semantic_intent=item.get("expected_semantic_intent"), tags=tuple(item.get("tags", ()))))
    return cases

def retrieval_evidence(case: EvaluationCase, retrieval: DebugResult) -> dict[str, Any]:
    raw = retrieval.local.get("retrieval", []); docs = raw if isinstance(raw, list) else []
    extracted = []
    for item in docs:
        if isinstance(item, dict):
            mapping = item.get("payload", {}).get("mapping")
            if isinstance(mapping, str) and "." in mapping: extracted.append(mapping.split(".")[0])
            elif isinstance(mapping, str): extracted.append(mapping)
    retrieved = sorted(set(extracted)); expected = set(case.expected_tables); matches = expected.intersection(retrieved)
    grounded = case.retrieval_ground_truth_available; top_k = int(retrieval.metrics.get("retrieval_result_count", len(docs)))
    precision = (len(matches) / len(retrieved)) if retrieved and grounded else (NOT_EVALUATED if not grounded else 0.0)
    recall = (len(matches) / len(expected)) if expected and grounded else (NOT_EVALUATED if not grounded else 0.0)
    results = [{"rank": i + 1, "score": d.get("score"), "document_type": d.get("object_type", UNAVAILABLE), "document_id": d.get("id", UNAVAILABLE)} for i, d in enumerate(docs) if isinstance(d, dict)]
    return {"status": retrieval.status, "result_count": len(docs), "results": results, "retrieved_tables": retrieved, "top_k": top_k, "latency_ms": retrieval.metrics.get("retrieval_latency_ms", UNAVAILABLE), "evaluation_not_available": not grounded, "expected_table_exact_match": (retrieved == sorted(expected)) if grounded else False, "table_precision": precision, "table_recall": recall, "retrieval_hit_at_k": bool(matches) if grounded else NOT_EVALUATED}

def failure_evidence(full: DebugResult, retrieval_ev: dict[str, Any]) -> dict[str, Any]:
    retrieval_failure = (retrieval_ev.get("retrieval_hit_at_k") is False) if retrieval_ev.get("retrieval_hit_at_k") != NOT_EVALUATED else NOT_EVALUATED
    return {"retrieval_failure":retrieval_failure,"generation_failure":UNKNOWN,"schema_hallucination":UNKNOWN,"semantic_hallucination":UNKNOWN,"validation_failure":False if full.status=="passed" else UNKNOWN,"correction_failure":UNKNOWN,"execution_correctness":NOT_EVALUATED,"root_cause":"retrieval_failure" if retrieval_failure is True else UNKNOWN,"evaluation_status":"evaluated" if retrieval_failure != NOT_EVALUATED else "partially_evaluated"}

def _generate_markdown_summary(run_id: str, prompt_version: str | None, model_label: str | None, metrics: dict[str, Any], reports: list[dict[str, Any]]) -> str:
    lines = [
        f"# Evaluation Summary Report",
        f"",
        f"**Run ID:** `{run_id}`  ",
        f"**Prompt Version:** `{prompt_version or 'default'}`  ",
        f"**Model Label:** `{model_label or 'default'}`  ",
        f"**Case Count:** `{metrics.get('case_count', 0)}`  ",
        f"",
        f"## Overall Metrics",
        f"",
        f"| Metric | Value |",
        f"| :--- | :--- |",
        f"| Validation Pass Rate | {metrics.get('validation_pass_rate', 0.0) * 100:.1f}% |",
        f"| Average Latency | {metrics.get('average_latency_ms', 0):.1f} ms |",
        f"| Retrieval Hit@K Rate | {metrics.get('retrieval_hit_at_k_rate', 0.0) * 100:.1f}% |",
        f"| Average Table Recall | {metrics.get('average_table_recall', 0.0) * 100:.1f}% |",
        f"| Average Table Precision | {metrics.get('average_table_precision', 0.0) * 100:.1f}% |",
        f"",
        f"## Case Breakdown",
        f"",
        f"| Case ID | Status | Latency (ms) | Retrieval Hit | Retrieved Tables |",
        f"| :--- | :--- | :--- | :--- | :--- |",
    ]
    for r in reports:
        case_id = r.get("case_id", "-")
        status = r.get("full", {}).get("status", "-")
        latency = r.get("full", {}).get("latency_ms", "-")
        lat_str = f"{latency:.1f}" if isinstance(latency, (int, float)) else str(latency)
        hit = r.get("retrieval", {}).get("retrieval_hit_at_k", "-")
        tables = ", ".join(r.get("retrieval", {}).get("retrieved_tables", []))
        lines.append(f"| `{case_id}` | **{status}** | {lat_str} | {hit} | {tables} |")
    return "\n".join(lines)

def evaluate(cases: list[EvaluationCase], observer: MLflowObserver | None=None, *, runner_factory: Callable[[], DebugRunner]=DebugRunner, prompt_version: str|None=None, model_label: str|None=None) -> dict[str, Any]:
    observer=observer or MLflowObserver(); run_id=str(uuid.uuid4()); reports=[]
    for case in cases:
        runner=runner_factory(); retrieval=runner.run(case.question,"retrieval"); full=runner.run(case.question,"full"); evidence=retrieval_evidence(case,retrieval)
        reports.append({"case_id":case.case_id,"question":case.question,"tags":list(case.tags),"ground_truth":{"expected_tables_available":case.retrieval_ground_truth_available,"expected_sql_available":bool(case.expected_sql),"semantic_intent_available":bool(case.expected_semantic_intent)},"retrieval":evidence,"full":{"status":full.status,"latency_ms":full.metrics.get("request_latency_ms",UNAVAILABLE),"validation_passed":full.metrics.get("validation_passed",UNAVAILABLE),"metadata":full.tags},"failure_analysis":failure_evidence(full,evidence)})
    count=len(reports); grounded=[item for item in reports if not item["retrieval"]["evaluation_not_available"]]
    latencies=[x["full"]["latency_ms"] for x in reports if isinstance(x.get("full", {}).get("latency_ms"), (int, float))]
    avg_latency=statistics.mean(latencies) if latencies else UNAVAILABLE
    metrics={"case_count":count,"successful_cases":sum(x["full"]["status"]=="passed" for x in reports),"failed_cases":sum(x["full"]["status"]!="passed" for x in reports),"validation_pass_rate":sum(float(x["full"]["validation_passed"]) for x in reports if isinstance(x["full"]["validation_passed"],(int,float)))/count if count else 0.0,"retrieval_ground_truth_case_count":len(grounded),"evaluation_not_available":not bool(grounded),"average_latency_ms":avg_latency}
    if grounded: metrics.update({"retrieval_hit_at_k_rate":sum(x["retrieval"]["retrieval_hit_at_k"] for x in grounded)/len(grounded),"average_table_precision":statistics.mean(x["retrieval"]["table_precision"] for x in grounded),"average_table_recall":statistics.mean(x["retrieval"]["table_recall"] for x in grounded)})
    report_data = {"evaluation_run_id":run_id,"configuration":{"prompt_version_label":prompt_version or UNAVAILABLE,"model_label":model_label or UNAVAILABLE,"model_execution":"production_default_only"},"metrics":metrics,"cases":reports}
    benchmark_dataset = [{"case_id": c.case_id, "question": c.question, "expected_tables": list(c.expected_tables), "tags": list(c.tags)} for c in cases]
    md_summary = _generate_markdown_summary(run_id, prompt_version, model_label, metrics, reports)

    observer.start({"run_type":"evaluation_summary","evaluation_run_id":run_id})
    observer.log_params({"prompt_version_label":prompt_version or UNAVAILABLE,"model_label":model_label or UNAVAILABLE,"evaluation_type":"dataset","case_count":count})
    observer.log(metrics={k:float(v) for k,v in metrics.items() if isinstance(v,(int,float))},tags={"correctness_measurement":"unavailable_without_equivalence_strategy","evaluation_run_id":run_id})
    observer.log_artifact_dict(report_data, "evaluation_report.json")
    observer.log_artifact_dict({"cases": benchmark_dataset}, "benchmark_dataset.json")
    observer.log_artifact_text(TEXT_TO_SQL_PROMPT, "prompt_template.txt")
    observer.log_artifact_text(md_summary, "evaluation_summary.md")
    observer.finish()
    return report_data

def comparison_matrix(reports: list[dict[str,Any]], baseline:int=0) -> dict[str,Any]:
    if not reports: raise ValueError("At least one evaluation report is required.")
    base=reports[baseline].get("metrics",{}); rows=[]
    base_config=reports[baseline].get("configuration",{})
    base_case_count=base.get("case_count")
    base_lat=base.get("average_latency_ms")
    if base_lat is None:
        base_cases=reports[baseline].get("cases", [])
        base_lats=[c.get("full", {}).get("latency_ms") for c in base_cases if isinstance(c.get("full", {}).get("latency_ms"), (int, float))]
        base_lat=statistics.mean(base_lats) if base_lats else UNAVAILABLE
    for report in reports:
        metrics=report.get("metrics",{}); comparable=("validation_pass_rate","retrieval_hit_at_k_rate","average_table_recall")
        regressions={key:metrics[key]<base[key] for key in comparable if isinstance(metrics.get(key),(int,float)) and isinstance(base.get(key),(int,float))}
        avg_lat=metrics.get("average_latency_ms")
        if avg_lat is None:
            cases=report.get("cases", [])
            lats=[c.get("full", {}).get("latency_ms") for c in cases if isinstance(c.get("full", {}).get("latency_ms"), (int, float))]
            avg_lat=statistics.mean(lats) if lats else UNAVAILABLE
        if isinstance(avg_lat, (int, float)) and isinstance(base_lat, (int, float)):
            regressions["average_latency_ms"] = avg_lat > base_lat
        cand_config = report.get("configuration", {})
        config_diff = {k: {"baseline": base_config.get(k), "candidate": cand_config.get(k)} for k in set(base_config) | set(cand_config) if base_config.get(k) != cand_config.get(k)}
        case_count_mismatch = bool(base_case_count is not None and metrics.get("case_count") is not None and metrics.get("case_count") != base_case_count)
        rows.append({"evaluation_run_id":report.get("evaluation_run_id",UNAVAILABLE),"configuration":cand_config,"configuration_differences":config_diff,"dataset_compatible":not case_count_mismatch,"validation_pass_rate":metrics.get("validation_pass_rate",UNAVAILABLE),"retrieval_hit_at_k_rate":metrics.get("retrieval_hit_at_k_rate",NOT_EVALUATED),"average_table_recall":metrics.get("average_table_recall",NOT_EVALUATED),"average_latency_ms":avg_lat,"regression_vs_baseline":regressions})
    return {"baseline_evaluation_run_id":reports[baseline].get("evaluation_run_id"),"rows":rows}
