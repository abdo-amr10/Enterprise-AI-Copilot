"""Evidence-based developer evaluation; it neither executes SQL nor judges with an LLM."""
from __future__ import annotations
import json, statistics, uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from src.observability.debug_runner import DebugResult, DebugRunner
from src.observability.mlflow_observer import MLflowObserver

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
        cases.append(EvaluationCase(item["case_id"], item["question"], item.get("expected_sql"), tuple(item.get("expected_tables", ())), tuple(item.get("expected_columns", ())), item.get("expected_semantic_intent"), tuple(item.get("tags", ()))))
    return cases

def _tables(results: list[dict[str, Any]]) -> set[str]:
    found=set()
    for item in results:
        payload=item.get("payload", {}) if isinstance(item, dict) else {}
        if not isinstance(payload, dict): continue
        mapping=payload.get("mapping")
        if isinstance(mapping, str) and mapping: found.add(mapping.split(".", 1)[0])
        found.update(value for key in ("from_table", "to_table") if isinstance((value:=payload.get(key)), str))
    return found

def retrieval_evidence(case: EvaluationCase, run: DebugResult) -> dict[str, Any]:
    documents=run.local.get("retrieval", []); documents=documents if isinstance(documents, list) else []
    actual=_tables(documents)
    results=[{"rank": rank, "score": doc.get("score", UNAVAILABLE), "document_type": doc.get("type", UNAVAILABLE), "document_id": doc.get("id", doc.get("name", UNAVAILABLE))} for rank, doc in enumerate(documents, 1) if isinstance(doc, dict)]
    base={"status":run.status,"result_count":len(documents),"results":results,"retrieved_tables":sorted(actual),"top_k":run.tags.get("top_k",UNAVAILABLE),"latency_ms":run.metrics.get("retrieval_latency_ms",UNAVAILABLE)}
    if not case.retrieval_ground_truth_available: return {**base,"evaluation_not_available":True,"expected_table_exact_match":NOT_EVALUATED,"table_precision":NOT_EVALUATED,"table_recall":NOT_EVALUATED,"retrieval_hit_at_k":NOT_EVALUATED}
    expected=set(case.expected_tables); overlap=actual & expected
    return {**base,"evaluation_not_available":False,"expected_table_exact_match":actual==expected,"table_precision":len(overlap)/len(actual) if actual else 0.0,"table_recall":len(overlap)/len(expected),"retrieval_hit_at_k":bool(overlap)}

def failure_evidence(full: DebugResult, retrieval: dict[str, Any]) -> dict[str, Any]:
    retrieval_failure=NOT_EVALUATED if retrieval["evaluation_not_available"] else not bool(retrieval["retrieval_hit_at_k"])
    return {"retrieval_failure":retrieval_failure,"generation_failure":UNKNOWN,"schema_hallucination":UNKNOWN,"semantic_hallucination":UNKNOWN,"validation_failure":False if full.status=="passed" else UNKNOWN,"correction_failure":UNKNOWN,"execution_correctness":NOT_EVALUATED,"root_cause":"retrieval_failure" if retrieval_failure is True else UNKNOWN,"evaluation_status":"evaluated" if retrieval_failure != NOT_EVALUATED else "partially_evaluated"}

def evaluate(cases: list[EvaluationCase], observer: MLflowObserver | None=None, *, runner_factory: Callable[[], DebugRunner]=DebugRunner, prompt_version: str|None=None, model_label: str|None=None) -> dict[str, Any]:
    observer=observer or MLflowObserver(); run_id=str(uuid.uuid4()); reports=[]
    for case in cases:
        runner=runner_factory(); retrieval=runner.run(case.question,"retrieval"); full=runner.run(case.question,"full"); evidence=retrieval_evidence(case,retrieval)
        reports.append({"case_id":case.case_id,"tags":list(case.tags),"ground_truth":{"expected_tables_available":case.retrieval_ground_truth_available,"expected_sql_available":bool(case.expected_sql),"semantic_intent_available":bool(case.expected_semantic_intent)},"retrieval":evidence,"full":{"status":full.status,"latency_ms":full.metrics.get("request_latency_ms",UNAVAILABLE),"validation_passed":full.metrics.get("validation_passed",UNAVAILABLE),"metadata":full.tags},"failure_analysis":failure_evidence(full,evidence)})
    count=len(reports); grounded=[item for item in reports if not item["retrieval"]["evaluation_not_available"]]
    metrics={"case_count":count,"successful_cases":sum(x["full"]["status"]=="passed" for x in reports),"failed_cases":sum(x["full"]["status"]!="passed" for x in reports),"validation_pass_rate":sum(float(x["full"]["validation_passed"]) for x in reports if isinstance(x["full"]["validation_passed"],(int,float)))/count if count else 0.0,"retrieval_ground_truth_case_count":len(grounded),"evaluation_not_available":not bool(grounded)}
    if grounded: metrics.update({"retrieval_hit_at_k_rate":sum(x["retrieval"]["retrieval_hit_at_k"] for x in grounded)/len(grounded),"average_table_precision":statistics.mean(x["retrieval"]["table_precision"] for x in grounded),"average_table_recall":statistics.mean(x["retrieval"]["table_recall"] for x in grounded)})
    observer.start({"run_type":"evaluation_summary","evaluation_run_id":run_id,"evaluation_type":"dataset","case_count":count,"prompt_version_label":prompt_version or UNAVAILABLE,"model_label":model_label or UNAVAILABLE}); observer.log(metrics={k:float(v) for k,v in metrics.items() if isinstance(v,(int,float))},tags={"correctness_measurement":"unavailable_without_equivalence_strategy","evaluation_run_id":run_id}); observer.finish()
    return {"evaluation_run_id":run_id,"configuration":{"prompt_version_label":prompt_version or UNAVAILABLE,"model_label":model_label or UNAVAILABLE,"model_execution":"production_default_only"},"metrics":metrics,"cases":reports}

def comparison_matrix(reports: list[dict[str,Any]], baseline:int=0) -> dict[str,Any]:
    if not reports: raise ValueError("At least one evaluation report is required.")
    base=reports[baseline].get("metrics",{}); rows=[]
    for report in reports:
        metrics=report.get("metrics",{}); comparable=("validation_pass_rate","retrieval_hit_at_k_rate","average_table_recall")
        regressions={key:metrics[key]<base[key] for key in comparable if isinstance(metrics.get(key),(int,float)) and isinstance(base.get(key),(int,float))}
        rows.append({"evaluation_run_id":report.get("evaluation_run_id",UNAVAILABLE),"configuration":report.get("configuration",{}),"validation_pass_rate":metrics.get("validation_pass_rate",UNAVAILABLE),"retrieval_hit_at_k_rate":metrics.get("retrieval_hit_at_k_rate",NOT_EVALUATED),"average_table_recall":metrics.get("average_table_recall",NOT_EVALUATED),"latency":UNAVAILABLE,"regression_vs_baseline":regressions})
    return {"baseline_evaluation_run_id":reports[baseline].get("evaluation_run_id"),"rows":rows}
