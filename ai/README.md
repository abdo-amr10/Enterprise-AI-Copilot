# Synthetic Banking Semantic Layer — Clean Architecture

This project contains the semantic-layer artifacts and the application/infrastructure code needed to use them.

## Architecture

```text
Dataset upload
    |
    +--> SchemaRepository / SchemaLoader
    |
    +--> prepared semantic artifacts
    |
    +--> SemanticLayerBuildService
              |
              +--> SemanticLayerLoader
              +--> optional embedding/index build
    |
    v
ACTIVE SEMANTIC LAYER (persisted)

User question
    |
    v
ContextRetrievalService
    |
    v
SemanticRepository
    |
    +--> local vector index / keyword fallback
    |
    v
semantic context
    |
    v
LLM / Text-to-SQL component
```

## Clean Architecture decisions

- Application code depends on ports, not infrastructure implementations.
- `ContextRetrievalService` depends only on `SemanticRepository`.
- Raw schema access belongs to the dataset-load/build phase.
- Query-time retrieval reads the persisted semantic layer; it does not regenerate it.
- Embedding and vector-store dependencies are isolated under infrastructure.
- Runtime configuration is kept under `src/config`.
- The LLM/Text-to-SQL component is intentionally not mixed into retrieval orchestration.
- Semantic artifacts are data, not hard-coded business logic.

## Replacement lifecycle

When a new database/schema is loaded:

1. Read and validate the new schema.
2. Prepare/review the semantic artifacts for that dataset.
3. Replace the active semantic-layer snapshot.
4. Rebuild the local vector index for the new snapshot.
5. Subsequent questions use the new snapshot.

The old semantic snapshot is removed when the new one becomes active.

## Query-time rule

The query path does **not** call `SchemaRepository`, `SchemaLoader`, or semantic generation. It retrieves from the stored semantic layer only.

## Human review

The supplied dataset metadata marks human review as required before production. The supplied business glossary and documentation are treated as the source for business meanings/rules; the LLM is not treated as an authority for approving them.
