# Semantic Layer Internal AI API

This document defines the AI runtime endpoints that the Backend calls while
implementing the public Semantic Layer APIs in the API specification.

They are internal compute APIs, not replacements for the public
`/api/v1/semantic-layer/*` endpoints. The Backend remains responsible for
authentication, source-file storage, revision persistence, versioning,
submission, status, and audit logging.

Base URL when running locally: `http://localhost:8000`.

## Endpoints

| Method | Path | Responsibility |
| --- | --- | --- |
| POST | `/internal/semantic/retrieve` | Retrieves context from the approved Semantic Layer. |
| POST | `/internal/semantic/generate-draft` | Runs FullRebuild or Incremental draft generation. |
| POST | `/internal/semantic/validate` | Validates a draft and runs the existing auto-fix retry loop. |
| POST | `/internal/semantic/review` | Applies the human approve/reject decision to a validated draft. |

`submit`, `status`, and `GET revision` do not have AI runtime endpoints. They
are Backend persistence operations from the public API contract.

## Generate Draft

`POST /internal/semantic/generate-draft`

```json
{
  "semanticLayerId": "sl-001",
  "triggerType": "FullRebuild",
  "sourceFileIds": {
    "schema": "file-schema-001",
    "documentation": "file-doc-001"
  },
  "resolvedSources": {
    "schema": { "tables": {} },
    "relationships": [],
    "documentation": "Database documentation",
    "business_glossary": "Business definitions",
    "sample_data": []
  }
}
```

`sourceFileIds` uses the public-contract names: `schema`, `documentation`,
`glossary`, and `sampleData`; `schema` is mandatory. `resolvedSources` is the
material loaded by the Backend and uses the AI builder names: `schema` and
`relationships` are required for FullRebuild; `documentation`,
`business_glossary`, and `sample_data` are optional.

For Incremental, add `baseRevisionId`, `baseSemanticLayer`, and
`affectedObjects`. Each affected object has exactly `section` and `id`.

```json
{
  "semanticLayerId": "sl-001",
  "triggerType": "Incremental",
  "sourceFileIds": { "schema": "file-schema-002" },
  "baseRevisionId": "rev-001",
  "affectedObjects": [{ "section": "measures", "id": "obj-123" }],
  "resolvedSources": { "schema": { "tables": {} } },
  "baseSemanticLayer": { "metadata": {}, "measures": [] }
}
```

Success response:

```json
{
  "status": "Success",
  "draft": {
    "metadata": {
      "semantic_layer_id": "sl-001",
      "revision_id": "rev-generated-by-ai"
    }
  }
}
```

The Backend must persist this draft and create its public `DraftGenerated`
response. `baseRevisionId` is deliberately metadata inside an Incremental
draft, not a field in the public generate-draft response. An Incremental
internal response also echoes `affectedObjects`, each containing only
`section` and `id`.

## Validate

`POST /internal/semantic/validate`

```json
{
  "draft": { "metadata": {}, "entities": [] },
  "schema": { "tables": {}, "relationships": [] }
}
```

The response is `{ "status": "Success", "draft": {...}, "validation":
{...} }`. The returned `draft` is authoritative because the auto-fixer may
have changed it. The Backend must persist both values and allow approval only
when `validation.status` is `passed`.

## Review

`POST /internal/semantic/review`

```json
{
  "draft": { "metadata": {} },
  "validation": { "status": "passed" },
  "decision": "Approve",
  "reviewerId": "usr-123",
  "comments": "Optional review note"
}
```

The response has `status` (`Approved` or `Rejected`), `draft`, and `review`.
The Backend derives `reviewerId` from its authenticated user; it must not trust
an arbitrary browser value.

## Errors and security

Malformed contracts return HTTP 422. These endpoints currently have no
machine-to-machine authentication, so the Backend deployment must place them
on a private network and add service authentication before exposure outside
that boundary.
