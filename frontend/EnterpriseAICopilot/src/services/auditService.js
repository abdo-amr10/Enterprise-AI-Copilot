import { request } from "./httpClient";

// GET /api/v1/audit-logs?Action=&From=&To=&UserId=
// All four are optional query params per the Swagger contract.
export function fetchAuditLogs({ action, from, to, userId } = {}) {
  const params = new URLSearchParams();
  if (action) params.set("Action", action);
  if (from) params.set("From", from);
  if (to) params.set("To", to);
  if (userId) params.set("UserId", userId);

  const query = params.toString();
  return request(`/api/v1/audit-logs${query ? `?${query}` : ""}`);
}
