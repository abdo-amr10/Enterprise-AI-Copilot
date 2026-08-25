"""Developer CLI for inspecting and evaluating the AI pipeline; it never executes SQL."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from src.observability.debug_runner import DebugRunner, LAYERS
from src.observability.evaluation import comparison_matrix, evaluate, load_dataset

SENSITIVE = {"prompt", "semantic_context", "generation", "final_sql", "retrieval", "self_correction_events", "local_error", "local_diagnostic"}

def main() -> int:
    parser = argparse.ArgumentParser(description="Developer-only AI observability and evaluation.")
    commands = parser.add_subparsers(dest="command", required=True)
    debug = commands.add_parser("debug"); debug.add_argument("layer", choices=LAYERS); debug.add_argument("--question", required=True); debug.add_argument("--show-local-output", action="store_true")
    evaluation = commands.add_parser("evaluate"); evaluation.add_argument("--dataset", required=True); evaluation.add_argument("--prompt-version"); evaluation.add_argument("--model-label")
    compare = commands.add_parser("compare"); compare.add_argument("--reports", nargs="+", required=True); compare.add_argument("--baseline", type=int, default=0)
    inspect = commands.add_parser("inspect-run"); inspect.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.command == "debug":
        result = DebugRunner().run(args.question, args.layer)
        local = result.local if args.show_local_output else {key: ("redacted (use --show-local-output locally)" if key in SENSITIVE else value) for key, value in result.local.items() if key == "flow" or key in SENSITIVE}
        print(json.dumps({"requested_layer": result.requested_layer, "prerequisites_executed": result.prerequisites, "stopping_point": result.stopping_point, "layers_not_executed": [x for x in LAYERS if x not in {*result.prerequisites, result.requested_layer}], "status": result.status, "metrics": result.metrics, "tags": result.tags, "local": local}, indent=2, default=str))
        return 0 if result.status == "passed" else 2 if result.status == "unsupported" else 1
    if args.command == "evaluate":
        print(json.dumps(evaluate(load_dataset(args.dataset), prompt_version=args.prompt_version, model_label=args.model_label), indent=2))
        return 0
    if args.command == "compare":
        reports = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.reports]
        print(json.dumps(comparison_matrix(reports, args.baseline), indent=2))
        return 0
    try:
        from mlflow.tracking import MlflowClient
        run = MlflowClient().get_run(args.run_id)
        print(json.dumps({"run_id": args.run_id, "metrics": run.data.metrics, "tags": run.data.tags}, indent=2))
        return 0
    except Exception as exc:
        print(f"Could not inspect MLflow run: {type(exc).__name__}")
        return 1

if __name__ == "__main__": raise SystemExit(main())
