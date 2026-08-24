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

`naturalLanguageQuery` is also accepted as a compatibility alias for
`question`. The response uses the established AI SQL contract:

```json
{"status":"Success","sql":"SELECT ..."}
```

## Backend-rejection correction request

When Backend RLS or database execution rejects the generated SQL, it may call
`POST /internal/copilot/correct-backend-rejection`.

```json
{
  "question": "Show transactions completed today",
  "sql": "SELECT ...",
  "backendError": "RLS_ERROR: Query must include branch filtering."
}
```

The response is the same `CopilotResponse` contract used by
`/text-to-sql`. The AI sends the Backend error to the correction model as a
confirmed issue, then re-runs syntax, schema, relationship, and critic checks
on the corrected SQL before returning it.

## Required Backend integration

The current Backend implementation calls `/text-to-sql` once and returns an
RLS/execution failure to the public caller. It does **not** currently call the
correction endpoint after an execution failure. Therefore an automatic
Backend-to-AI retry cannot occur until Backend adds that single internal call.

This is an integration requirement, not a change to RLS ownership or RLS
logic. The Backend remains the only component that decides whether an RLS
failure occurred and whether a retry is permitted.

## Retry safety

- Send only the original natural-language question, the rejected SQL, and the
  Backend error. Do not send a JWT, branch identifier, connection string, or
  raw database data to the AI runtime.
- Limit the Backend retry count and stop after a non-retryable error.
- Execute only the SQL returned with `status: "Success"`.
- Keep Backend validation and parameter binding active for every retry.
