# Backend RLS-Rejection Retry Contract

## Purpose and ownership

The Backend owns authentication, the authenticated user's branch identity,
Row-Level Security (RLS) enforcement, SQL execution, and retry decisions. The
AI runtime owns SQL generation, correction, and deterministic SQL validation.

The AI runtime does not receive a branch ID and must never apply an RLS policy
or substitute a branch value in a query.

## Initial SQL request

The existing Backend client calls `POST /internal/copilot/text-to-sql`.

```json
{"question":"Show transactions completed today"}
```

The response uses the established AI SQL contract:

```json
{"status":"Success","sql":"SELECT ..."}
```

## Backend-rejection retry

There is no separate correction endpoint. When Backend RLS or database
execution rejects generated SQL, the Backend may re-call the same route with
the original question and one system conversation message:

```json
{
  "question": "Show transactions completed today",
  "conversation": [
    {
      "role": "system",
      "content": "RLS_CORRECTION: The previous SQL was 'SELECT ...'. It failed with 'RLS_ERROR: Query must include branch filtering.'. Generate a replacement SQL query that fixes this exact policy failure while preserving the original question."
    }
  ]
}
```

The runtime extracts only `RLS_CORRECTION:` system messages as correction
feedback. It then generates a replacement and runs its regular read-only,
syntax, schema, relationship, critic, and self-correction checks before
returning the same response contract.

## Retry safety

- Send only the original natural-language question, the rejected SQL, and the
  Backend error. Do not send a JWT, branch identifier, connection string, or
  raw database data to the AI runtime.
- Limit the Backend retry count and stop after a non-retryable error.
- Execute only the SQL returned with `status: "Success"`.
- Keep Backend validation and parameter binding active for every retry.
- Backend remains the sole RLS authority; this feedback helps SQL generation
  but is not an authorization decision.
