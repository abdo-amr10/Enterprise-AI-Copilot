# Enterprise AI Copilot Runtime

This service generates and validates read-only SQL. It never connects to a
production database or executes SQL. Backend owns authentication,
authorization, RLS, execution, history, and persistence.

## Runtime flow

```text
POST /internal/copilot/text-to-sql
  -> approved semantic retrieval
  -> Text-to-SQL generation (Ollama through LLMClient)
  -> structured-response and independent read-only checks
  -> syntax -> schema -> relationship -> parameterized RLS-shape validation
  -> SQL critic -> verified findings -> correction (with prompt-facing rejected candidates history)
  -> at most 3 corrections (with deterministic AST oscillation detection)
  -> validated SQL returned to Backend
  -> Backend executes SQL
  -> optional Backend RLS/execution rejection retry
  -> Backend re-calls POST /internal/copilot/text-to-sql with RLS_CORRECTION feedback in conversation
  -> AI correction -> validation -> corrected SQL returned to Backend
  -> POST /internal/copilot/format-execution-result
  -> deterministic text/table/Excel response
```

The critic is always called after deterministic validation succeeds. Its
findings are advisory and table/column claims are checked against the physical
schema before correction. Each correction step receives a `<REJECTED_CANDIDATES>`
history of prior failed queries from the active run to prevent oscillation. Every
corrected statement runs the complete deterministic and critic sequence again.

The Backend remains the sole authority for authentication and the actual branch
value. The AI validates the required *parameterized SQL shape* from the
Backend's RLS mapping: it emits `@UserBranchId` and the required joins, while
the Backend binds that parameter from the JWT and enforces execution. If the
Backend rejects an already validated SQL statement, it retries the same
internal route with the rejected SQL and error in a system `RLS_CORRECTION:`
conversation message. See
[the Backend RLS-rejection retry contract](docs/backend-rls-retry-contract.md)
for the exact handoff and the required Backend call.

## Model configuration

- Embeddings: `BAAI/bge-m3`, provisioned at `models/embeddings/bge-m3`.
  The model is loaded lazily and offline with `local_files_only=True`; it has
  1024 dimensions and creates normalized float32 vectors.
- Semantic index: FAISS `IndexFlatIP` over BGE-M3 vectors, with revision and
  model metadata validation.
- Generation, critic, correction: `qwen2.5-coder:7b` through the configured
  `OllamaClient`. Set `OLLAMA_HOST` and `OLLAMA_TIMEOUT_SECONDS` as needed.

Model artifacts are deployment-provisioned and must not be committed to Git.
Install project dependencies, then build the local development index only when
using the retained local retrieval fixture:

```powershell
cd ai
python -m pip install -e ".[dev]"
python -m scripts.build_semantic_index
```

When `AI_LOCAL_DEV_MODE=true`, the Text-to-SQL command also builds this
derived FAISS index automatically if it is missing. Running the build command
directly remains useful for preparing the local artifact ahead of time.

## Ownership boundaries

Semantic generation, validation, review, embedding, and index building process
Backend-provided values in memory. Backend owns source uploads, revisions,
approval lifecycle, and persistence. The currently retained local
`FileSemanticRepository` and FAISS artifact support local retrieval/testing;
their Backend-owned retrieval migration is a separate integration concern.

`POST /internal/copilot/format-execution-result` receives a minimal,
storage-neutral Backend execution-result payload. Small results are returned
inline. Results over the configured inline-row limit are returned as an
in-memory Base64 Excel payload for Backend delivery; no AI-side result file is
persisted. PDF output is intentionally not implemented because the current
Backend contract supplies no report-template or PDF policy.

## Local SQL validation/correction test

This requires the local approved semantic artifact/index, BGE-M3, FAISS, and
the configured Ollama models. It does not execute SQL:

```powershell
cd ai
python -m scripts.test_text_to_sql_self_correction --question "Show all customers"
```

It prints the semantic context, generated SQL, deterministic findings, critic
status, each correction, final SQL, and correction count.

## Tests

```powershell
cd ai
pytest
```

For a package-level architecture and ownership map, see
[AI Runtime Documentation Guide](docs/ai-runtime-documentation.md).

See `docs/semantic-layer-architecture.html` for the Backend-owned Semantic
Layer lifecycle.

## Promote a successful live Semantic Layer test

The live Semantic Layer integration test creates timestamped output folders.
To use its newest approved result with the local Text-to-SQL runtime, run:

```powershell
cd ai
python -m scripts.use_latest_live_semantic_artifact
$env:AI_LOCAL_DEV_MODE = "true"
```

The command verifies approval, validation, and review result files before
copying the approved layer and index artifacts to `outputs/semantic_layer/`.
Use `--dry-run` to inspect the selected artifact, or `--artifact-dir <path>`
to choose one explicitly.

To promote that artifact automatically immediately before a local question:

```powershell
$env:AI_LOCAL_DEV_MODE = "true"
python scripts/run_text_to_sql_pipeline.py --use-latest-approved-semantic --question "Show all customers" --verbose
```
