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
          -> correction #1 -> complete validation/critic sequence
          -> correction #2 -> complete validation/critic sequence
          -> correction #3 -> complete validation/critic sequence
          -> success or MAX_RETRIES_EXCEEDED
```

Syntax validation precedes schema validation, which precedes relationship
validation. The critic is called after that deterministic sequence passes and
is not trusted without `CriticFindingVerifier` grounding its references.

## Backend responsibilities

Backend handles credentials, authorization, RLS, SQL Server connection and
execution, query history, revision persistence, and delivering artifacts to
the user. AI returns only validated read-only SQL or a stable failure code.
