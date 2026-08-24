# AI Runtime Documentation Guide

## Scope and ownership

`src/` is the AI runtime. It generates and validates SQL but never connects to
the production database, executes a query, enforces RLS, creates public
reports, or persists user history. Those actions are Backend-owned.

## Package map

| Package | Responsibility |
|---|---|
| `src/api` | FastAPI boundary, Pydantic request/response contracts, and dependency composition. |
| `src/application/dto` | Immutable request, response, validation, and workflow data structures. |
| `src/application/pipelines` | Orchestration for semantic retrieval, semantic-layer lifecycle, and Text-to-SQL. |
| `src/application/services/self_correction` | Syntax, schema, relationship validation; critic verification; and bounded SQL correction. |
| `src/application/services/semantic_layer` | Build, merge, identity, validation, human-review, and embedding workflows. |
| `src/application/services/text_to_sql` | Context assembly and SQL-generation invocation. |
| `src/application/ports` | Interfaces that separate application behavior from Ollama, Backend HTTP, and storage adapters. |
| `src/infrastructure` | Ollama, Backend HTTP, schema, embedding, FAISS, and repository implementations. |
| `src/prompts` | Versioned, task-specific LLM prompt templates. |
| `src/config` | Typed runtime configuration defaults. |

## Internal HTTP contracts

| Route | Purpose | Backend role |
|---|---|---|
| `POST /internal/copilot/text-to-sql` | Generate and internally validate read-only SQL. | Send question; execute only successful SQL. |
| `POST /internal/copilot/correct-backend-rejection` | Correct SQL rejected by Backend RLS/execution, then re-run AI validation. | Call only after a retryable Backend rejection. |
| `POST /internal/copilot/format-execution-result` | Format a Backend-owned result without executing SQL. | Supply the execution result. |
| `POST /internal/semantic/retrieve` | Retrieve approved semantic context. | Provide the question. |
| `POST /internal/semantic/generate-draft` | Generate an unpersisted Semantic Layer draft. | Own source files and revision persistence. |
| `POST /internal/semantic/validate` | Validate an unpersisted Semantic Layer draft. | Supply schema, relationships, and optional semantic sources. |
| `POST /internal/semantic/review` | Apply a human review decision. | Authenticate and authorize the reviewer. |

## Text-to-SQL correction sequence

1. The runtime retrieves approved semantic context once.
2. It generates a structured, read-only SQL candidate.
3. It validates syntax, physical schema references, and approved joins.
4. A critic evaluates whether the valid SQL answers the question; its claims
   are filtered through `CriticFindingVerifier` before correction.
5. A correction is attempted only for a confirmed issue and is revalidated
   from step 3. The default limit is three corrections.
6. Backend enforces RLS and executes the SQL. A later Backend rejection may
   enter the separate retry contract documented in
   [backend-rls-retry-contract.md](backend-rls-retry-contract.md).

## Documentation convention

Public workflow classes and integration boundaries must document their owner,
input/output contract, and security boundary. Short DTOs, typed configuration,
and abstract port declarations use their type names and field annotations as
their primary API documentation; they should receive a docstring when their
meaning is not obvious from those types.

When adding a route, update this guide, `README.md`, the relevant handoff
document, and a contract test in the same commit.
