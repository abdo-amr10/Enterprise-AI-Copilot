# Copilot Runtime Handoff

## AI-owned contracts

The AI runtime implements the internal semantic retrieval contract:

`POST /internal/semantic/retrieve`

Request shape:

```json
{"question":"...","conversation":[]}
```

Response shape:

```json
{"status":"Success","context":{"tables":[],"businessRules":[]}}
```

For `POST /api/v1/copilot/ask`, the Backend calls `CopilotRuntimePipeline`.
It returns either a read-only SQL string or `SQL_GENERATION_FAILED` / 
`SQL_VALIDATION_FAILED`. The Backend must apply authorization and RLS, execute
the SQL, build the public `report`, and store history. Query history endpoints
are Backend-owned and deliberately have no AI implementation.

## Recommended internal Text-to-SQL handoff

The public PDF specifies `POST /api/v1/copilot/ask`, but it does not name the
Backend-to-AI-Runtime route. The integration transcript uses the following
recommended internal contract so Backend and AI implementations can be tested
independently:

`POST /internal/copilot/text-to-sql`

Request:

```json
{"question":"Show total revenue for active customers.","conversation":[]}
```

Successful response:

```json
{"status":"Success","sql":"SELECT ...;"}
```

Failure response:

```json
{"status":"Failed","sql":null,"errorCode":"SQL_VALIDATION_FAILED","message":"..."}
```

This is an internal handoff only. The Backend must not return the SQL to the
frontend; it executes the approved SQL and returns the public `report` contract.
