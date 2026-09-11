import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { HOME_BY_ROLE } from "../config/routes";
export default function RoleRoute({ role, roles }) {
  const { user } = useAuth();
  const allowedRoles = roles || [role];
  return allowedRoles.includes(user?.role) ? (
    <Outlet />
  ) : (
    <Navigate to={HOME_BY_ROLE[user?.role] || "/login"} replace />
  );
}
