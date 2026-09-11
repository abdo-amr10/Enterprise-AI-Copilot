# AI observability and evaluation (developer-only)

This layer is separate from the API and production composition root. It reuses
the existing services, never executes SQL, never creates query history, and
never writes to the Backend database.

## Setup and commands

Install MLflow only when local recording is wanted:

```powershell
cd ai
python -m pip install -e ".[dev,observability]"
$env:OBSERVABILITY_ENABLED = "true"
$env:OBSERVABILITY_TRACKING_URI = "http://127.0.0.1:5000"
mlflow server --host 127.0.0.1 --port 5000
python -m scripts.observability debug full --question "Show total sales by region"
python -m scripts.observability debug retrieval --question "Show total sales by region"
python -m scripts.observability debug prompt --question "Show total sales by region" --show-local-output
python -m scripts.observability evaluate --dataset docs/evaluation-dataset.example.json
python -m scripts.observability compare --reports report-a.json report-b.json --baseline 0
python -m scripts.observability inspect-run --run-id <mlflow-run-id>
```

`--show-local-output` can display prompt/context/generated SQL in the terminal.
It does not change MLflow's allowlist and should not be used in shared logs.

The available target layers are `retrieval`, `prompt`, `generation`,
`validation`, `critic`, `correction`, and `full`. `validation`, `critic`, and
`correction` are reported as unsupported because the current production
contract exposes no safe independent stopping boundary. `full` calls the real
`CopilotRuntimePipeline.run` path and stops at its validated-SQL boundary.

## Configuration

`OBSERVABILITY_ENABLED=false` is the default. When false, MLflow is not
imported or initialized and no tracking/network request is made.

- `OBSERVABILITY_TRACKING_URI` (or `MLFLOW_TRACKING_URI`)
- `OBSERVABILITY_EXPERIMENT_NAME` (default `enterprise-ai-copilot`)
- `OBSERVABILITY_TRACE_SAMPLE_RATE` (0.0–1.0; default 0.0)
- `OBSERVABILITY_TOTAL_LATENCY_THRESHOLD_MS`
- `OBSERVABILITY_RETRIEVAL_LATENCY_THRESHOLD_MS`
- `OBSERVABILITY_LLM_LATENCY_THRESHOLD_MS`
- `OBSERVABILITY_LOW_RETRIEVAL_SCORE`

All debug runs request full detail. Other users of the adapter can use the
policy's error/zero-result/latency/sample reasons. No MLflow autologging is
enabled.

## Recorded data and versioning

The MLflow allowlist contains only tags and numeric metrics: run type/layer,
prompt source SHA-256, configured model identifier/runtime/limits, embedding
and FAISS metadata when exposed by the existing runtime, safe latency/count
metrics, status, and error type. Raw question, prompt, SQL, semantic source
text, model response, user identifiers, credentials, and exception text are
never logged.

For targeted retrieval/prompt/generation commands, the observer records spans
that remain open during the actual selected operation. For `full`, it records
one request span around the real runtime orchestration. It does not fabricate
internal retrieval/prompt/generation/validator/critic/correction spans for the
full path because those components expose no safe production observer boundary.

Prompt identity is a deterministic SHA-256 of the existing prompt source;
there is no invented prompt version. Ollama exposes a configured model name but
not an exact model build/version through the current DTO, so `model_version`
is recorded as `unavailable`. Token metrics are also `unavailable`: the
production response DTO deliberately exposes only text and has not been
changed for observability. Embedding/index metadata is emitted only when the
existing repository/index exposes it; otherwise it is `unavailable`.

Index lifecycle is observed from the existing repository's revision cache:
`index_created`, `index_reused`, and `index_rebuilt` indicate the before/after
state of that cache for the debug run. The underlying production repository
does not expose separate build, query-embedding, or FAISS-search timers, so
those timings are not fabricated; the recorded retrieval timing is end-to-end.

## Evaluation

Datasets are local JSON and developer owned. A case needs `case_id` and
`question`; `expected_sql`, `expected_tables`, and `tags` are optional.
The runner reports success/validation pass rates, latency, and correction
attempts. It intentionally does not report SQL accuracy or table-match rate
without a supplied, agreed SQL-equivalence rule and a production-safe output
observer boundary.

Phase 3 adds evidence-only retrieval evaluation. Cases can include
`expected_tables`, `expected_columns`, `expected_sql`, and
`expected_semantic_intent`. Only `expected_tables` is currently evaluated:
exact expected-table match, precision, recall, and hit@k are defined from the
tables represented by real retrieved documents. Without expected tables,
`evaluation_not_available` is true; no quality score is invented.

Each case has independent states for `retrieval_failure`, `generation_failure`,
`schema_hallucination`, `semantic_hallucination`, `validation_failure`,
`correction_failure`, and `execution_correctness`. A state is `unknown` or
`not_evaluated` when the real production contract lacks sufficient evidence.
Validation success is not treated as proof of no hallucination. SQL execution
is never performed, so execution correctness is always `not_evaluated`.

`compare` compares saved evaluation reports and flags only observable
regressions in validation pass rate and retrieval ground-truth metrics. It does
not mutate model or prompt configuration. `--prompt-version` and
`--model-label` are developer labels paired with the real recorded prompt hash
and production-default model metadata; they do not change inference.
