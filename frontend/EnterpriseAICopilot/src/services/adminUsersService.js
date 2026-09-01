import { request } from "./httpClient";
import { toApiRole } from '../config/roles'

// Wraps the 4 confirmed backend endpoints (Swagger UI, runasp.net backend).
// Request/response shapes are taken exactly from the Swagger schemas
// provided — nothing here is invented or assumed.
//
// The shared HTTP client adds the active administrator's JWT automatically.

// POST /api/v1/Auth/register
// Body: { firstName, lastName, email, password, confirmPassword, role, branchId }
export function registerUser({ firstName, lastName, email, password, confirmPassword, role, branchId }) {
  const apiRole = toApiRole(role)
  return request("/api/v1/Auth/register", {
    method: "POST",
    body: JSON.stringify({ firstName, lastName, email, password, confirmPassword, role: apiRole, branchId }),
  });
}

// POST /api/v1/Auth/admin/change-password
// Body: { email, newPassword, confirmPassword }
export function changeUserPassword({ email, newPassword, confirmPassword }) {
  return request("/api/v1/Auth/admin/change-password", {
    method: "POST",
    body: JSON.stringify({ email, newPassword, confirmPassword }),
  });
}

// DELETE /api/v1/Auth/delete-user?Email={email}
// Email is a query parameter, not a body field, per the Swagger contract.
export function deleteUser({ email }) {
  return request(`/api/v1/Auth/delete-user?Email=${encodeURIComponent(email)}`, {
    method: "DELETE",
  });
}

// PUT /api/v1/Auth/admin/update-role
// Body: { email, newRole }
export function updateUserRole({ email, newRole }) {
  const apiRole = toApiRole(newRole)
  return request("/api/v1/Auth/admin/update-role", {
    method: "PUT",
    body: JSON.stringify({ email, newRole: apiRole }),
  });
}
