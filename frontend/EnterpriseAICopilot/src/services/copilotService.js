import { request } from "./httpClient";

// POST /api/v1/copilot/ask
// Body: { question, conversation: [{ role, content }] }
// Success: { queryId, status: "Completed", report: { textSummary, presentationType, data } }
// Failure: { queryId, status: "Failed", errorCode, message }
export function askCopilot({ question, conversation = [] }) {
  return request("/api/v1/copilot/ask", {
    method: "POST",
    body: JSON.stringify({ question, conversation }),
  });
}
