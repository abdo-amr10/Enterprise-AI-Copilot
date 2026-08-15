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
