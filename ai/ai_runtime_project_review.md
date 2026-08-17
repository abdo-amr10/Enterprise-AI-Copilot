# Enterprise AI Copilot - Project Review

## Executive summary

The repository contains an AI runtime and supporting Semantic Layer pipeline.
The AI-owned core is implemented and unit-tested, including semantic retrieval,
Text-to-SQL generation, read-only SQL protection, and a new self-correction
loop. The repository now also contains a FastAPI AI-runtime service.

The API specification is **not fully implemented as HTTP APIs**. Only the two
AI-internal routes are mounted in FastAPI. Semantic Layer HTTP endpoints are
currently exercised through mocks and client contracts, while authentication,
RLS, SQL execution, history, audit, and public Copilot reporting remain
Backend responsibilities.

## Repository map

| Path | Purpose |
|---|---|
| `README.md` | Root-level project introduction. |
| `docs/database_metadata/` | Source schema, documentation, glossary, and sample data used to build the Semantic Layer. |
| `ai/main.py` | FastAPI application entry point. It mounts the internal Copilot and semantic-retrieval routers. |
| `ai/pyproject.toml` | Python package metadata, runtime dependencies, development dependencies, and pytest configuration. |
| `ai/src/api/` | HTTP boundary. `dependencies.py` builds and caches runtime dependencies; `routers/` exposes FastAPI endpoints. |
| `ai/src/application/` | Use cases, DTOs, pipelines, and ports. This layer contains the business workflow. |
| `ai/src/infrastructure/` | Adapters for Ollama, files, embeddings, vector retrieval, schema loading, and Backend HTTP clients. |
| `ai/src/prompts/` | Prompts for full/incremental semantic builds, Text-to-SQL, SQL critic, and SQL correction. |
| `ai/scripts/` | Command-line helpers for building the Semantic Layer/index and running the local Text-to-SQL flow. |
| `ai/outputs/semantic_layer/` | Generated approved Semantic Layer, index, and review/build artifacts. |
| `ai/tests/unit/` | Deterministic tests for DTOs, pipelines, services, and infrastructure adapters. |
| `ai/tests/integration/` | Mocked Backend/Copilot transcripts and real-infrastructure tests for Ollama when available. |
| `backend/` | Reserved for the Backend implementation; currently has no application source. |
| `frontend/` | Reserved for the frontend implementation; currently has no application source. |

## AI runtime architecture

### Semantic Layer build-time flow

1. Source files are loaded from `docs/database_metadata/`.
2. The source schema is normalized and mapped.
3. An LLM creates a FullRebuild or Incremental semantic draft.
4. The draft is validated and may be auto-fixed.
5. Human review approves or rejects the revision.
6. The approved layer is indexed for runtime retrieval.

Key code:

- `ai/src/application/pipelines/semantic_layer/semantic_layer_generation_pipeline.py`
- `ai/src/application/services/semantic_layer/`
- `ai/src/infrastructure/semantic_layer/`
- `ai/tests/integration/semantic_layer_test_scripts/`

### Runtime question flow

1. The Backend sends a question to the AI runtime.
2. The runtime retrieves relevant approved semantic context.
3. The Text-to-SQL pipeline builds a grounded prompt and calls Ollama.
4. `CopilotRuntimePipeline` rejects malformed, empty, or write-capable SQL.
5. The self-correction loop validates syntax, schema references, and approved
   relationships; it may invoke an LLM critic and correction pass.
6. The runtime returns safe SQL to the Backend. The Backend applies RLS,
   executes SQL, stores query history, and returns a report to the frontend.

Key code:

- `ai/src/application/pipelines/context_retrieval/semantic_retrieval_pipeline.py`
- `ai/src/application/pipelines/text_to_sql/copilot_runtime_pipeline.py`
- `ai/src/application/services/text_to_sql/`
- `ai/src/application/services/self_correction/`
- `ai/src/api/dependencies.py`

## API review against the specification

### Implemented FastAPI routes

| Route | Status | Notes |
|---|---|---|
| `GET /health` | Implemented | Operational health check; not part of the supplied API specification. |
| `POST /internal/semantic/retrieve` | Implemented | Response contract matches the specified `status/context/tables/businessRules` shape. |
| `POST /internal/copilot/text-to-sql` | Implemented internal extension | Returns `status`, safe SQL or an AI error code. This internal route is recommended because the PDF names the public route but not the Backend-to-AI route. |

### Specification coverage

| Module / route | Current status | Owner / next action |
|---|---|---|
| `POST /api/v1/auth/login` | Not implemented | Backend: JWT authentication. |
| `POST /api/v1/auth/register` | Not implemented | Backend: users, roles, branches, creator audit. |
| Semantic Layer upload, source retrieval, draft, revision, review, submit, status | Contract and mock integration implemented; no FastAPI routes | Backend implements persistence/controllers; AI service receives generation/review handoffs as agreed. |
| `POST /api/v1/copilot/ask` | Public endpoint not implemented | Backend calls AI internal Text-to-SQL, applies authorization/RLS, executes SQL, creates `queryId` and `report`. |
| `GET /api/v1/copilot/history` | Not implemented | Backend: query storage and per-user filtering. |
| `GET /api/v1/copilot/history/{queryId}` | Not implemented | Backend: ownership validation and stored formatted result. |
| `POST /internal/semantic/retrieve` | Implemented | AI-owned route. Internal authentication still needs agreement/implementation. |
| `GET /api/v1/audit-logs` | Not implemented | Backend: immutable audit store and filtering. |
| Standard HTTP error contract | Partially implemented | AI returns SQL error codes, but there is no shared FastAPI exception handler or HTTP-status mapping. |

## Semantic Layer contract status

The integration transcript in
`ai/tests/integration/semantic_layer_test_scripts/transcript.json` verifies
the agreed contract changes:

- FullRebuild receives the upload-created `semanticLayerId`.
- Revision and status routes include `semanticLayerId` in their path.
- Submit uses `POST /api/v1/semantic-layer/{semanticLayerId}/revisions/{revisionId}/submit` with `{}`.
- Incremental `affectedObjects` uses only `{ "section", "id" }`.
- Incremental generation response includes `affectedObjects`.
- Generate-draft response omits `baseRevisionId`.

These are **contract/mocked integration checks**, not live FastAPI endpoints.

## Copilot contract status

The integration transcript in `ai/tests/integration/copilot_test_scripts/`
contains:

- Semantic retrieval success.
- Public Copilot success shape with `queryId`, `Completed`, and `report`.
- Write-SQL rejection with `SQL_VALIDATION_FAILED`.

The public report in this transcript is a Backend mock. In production, only
the Backend can create it because it owns RLS and database execution.

## Test status

Verified in this workspace:

```text
53 unit tests passed
2 selected integration tests passed
```

Run tests:

```powershell
cd ai
python -m pytest tests/unit
python -m pytest tests/integration/copilot_test_scripts/test_copilot_runtime_transcript.py tests/integration/backend/test_semantic_layer_backend_flow.py
```

Run the AI service after installing dependencies:

```powershell
cd ai
python -m pip install -e ".[dev]"
uvicorn main:app --reload --port 8000
```

## Gaps to address before production handoff

### AI runtime work

1. Replace raw `dict` request bodies in FastAPI routers with Pydantic models.
   Missing fields currently risk an unhandled `KeyError` rather than a standard
   `INVALID_REQUEST` response.
2. Add a FastAPI exception handler that produces the shared error contract and
   correct HTTP statuses.
3. Add internal service authentication for both AI routes.
4. Use `conversation` in retrieval/prompt construction, or remove it from the
   internal contract if it is not required.
5. Add tests for schema validator, relationship validator, critic, correction,
   correction retries, and FastAPI routes.
6. Add a deployment/CI test that starts FastAPI and verifies `/openapi.json`.

### Backend work

1. Implement all public Auth, Semantic Layer, Copilot history, Audit, and
   public Copilot endpoints.
2. Own JWT, roles, ownership checks, RLS, database execution, report
   formatting, history storage, and audit logging.
3. Call the AI routes only through authenticated internal networking.
4. Map AI errors such as `SQL_GENERATION_FAILED`, `SQL_VALIDATION_FAILED`, and
   `MAX_RETRIES_EXCEEDED` to the shared public error contract.

## Repository hygiene

- Do not commit `__pycache__/`, `*.pyc`, temporary test directories, or
  rendered PDF pages under `tmp/`.
- Add a `.gitignore` if these generated artifacts are not already excluded.
- Install dependencies from `ai/pyproject.toml`; `requirements.txt` is no
  longer the dependency source.
