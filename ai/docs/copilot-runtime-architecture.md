# Copilot runtime architecture

The AI service has four independent processing boundaries:

1. Semantic Layer generation/validation/review. Backend owns all revision and
   source-file persistence; AI performs processing only.
2. Semantic retrieval. The retained local development adapter loads the
   approved Semantic Layer and a compatible BGE-M3 FAISS index. It builds a
   compact join-complete context once per question.
3. Text-to-SQL. The LLM returns a strict JSON contract. The runtime rejects
   malformed JSON, non-success payloads, missing SQL, false read-only flags,
   and forbidden T-SQL operations before correction begins.
4. Post-query formatting. Backend executes SQL, then may send only a normalized
   result payload to `/internal/copilot/format-execution-result`. AI never
   receives a driver/cursor and never executes SQL.

## Correction loop

The correction count is exactly three maximum actual correction calls:

```text
initial SQL -> deterministic validators -> critic -> verified findings
          -> record candidate in rejected_candidates history
          -> correction #1 (receives current issues + rejected history)
          -> complete validation/critic sequence
          -> correction #2 (receives current issues + accumulated rejected history)
          -> complete validation/critic sequence
          -> correction #3 (receives current issues + accumulated rejected history)
          -> success, CORRECTION_OSCILLATION, or MAX_RETRIES_EXCEEDED
```

Syntax validation precedes schema validation, which precedes relationship
validation. The critic is called after that deterministic sequence passes and
is not trusted without `CriticFindingVerifier` grounding its references.

### Proactive & Deterministic Oscillation Prevention
1. **Proactive LLM Guidance (`rejected_candidates`):** Each correction attempt receives a formatted `<REJECTED_CANDIDATES>` history of previously failed SQL queries and their specific rejection issues from the active run. Active `<ISSUES>` contains only the current candidate's problems.
2. **Deterministic Safeguard (`seen_fingerprints`):** SHA-256 AST hashing detects repeat query states after generation and terminates the loop immediately upon repeat.

## Backend responsibilities & Error Reporting

Backend handles credentials, authorization, RLS, SQL Server connection and
execution, query history, revision persistence, and delivering artifacts to
the user. AI returns only validated read-only SQL or a stable failure response.

When self-correction fails:
- The AI runtime returns `isSuccess: false`, `generatedSql: null`, and `errorMessage: <failure_reason>` containing the exact confirmed validation issues.
- The Backend (`CopilotService.cs`) records the failure reason into `CopilotQueryHistories.ErrorMessage` and registers an audit log event (`AuditActions.QueryFailed`).
