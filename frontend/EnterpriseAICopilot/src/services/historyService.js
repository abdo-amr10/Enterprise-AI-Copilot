import { request } from "./httpClient";

// GET /api/v1/copilot/history
// Response: { items: [{ queryId, question, status, createdAt }] }
export function fetchHistory() {
  return request("/api/v1/copilot/history");
}

// GET /api/v1/copilot/history/{queryId}
// Response: { queryId, question, status, createdAt, result: { textSummary, presentationType, data? } }
export function fetchHistoryItem(queryId) {
  return request(`/api/v1/copilot/history/${encodeURIComponent(queryId)}`);
}
