import { useAuth } from "../context/useAuth";
import { ROLES } from "../config/roles";
import AppSidebar from "./AppSidebar";
import AdminSidebar from "./AdminSidebar";

export default function Sidebar({ active }) {
  const { user } = useAuth();

  if (user?.role === ROLES.ADMIN) {
    return <AdminSidebar active={active} />;
  }

  return <AppSidebar active={active} />;
}