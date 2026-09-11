import { Link } from "react-router-dom";
import Logo from "../assets/Logo.png";
import { NAVIGATION_BY_ROLE } from "../config/routes";
import { ROLES } from "../config/roles";
import { useAuth } from "../context/useAuth";
import { IconDashboard, IconHistory, IconLayers, IconShieldCheck, IconSparkles, IconUsers } from "./icons";
import SidebarProfile from './SidebarProfile'

const icons = { copilot: IconSparkles, history: IconHistory, dashboard: IconDashboard, semantic: IconLayers, users: IconUsers, audit: IconShieldCheck };

export default function AdminSidebar({ active }) {
  const { logout, user } = useAuth();

  return (
    <aside className="admin-sidebar">
      <Link className="admin-logo" to="/admin">
        <img src={Logo} alt="" />
        <span>
          Enterprise
          <br />
          <b>AI</b> Copilot
        </span>
      </Link>
      <p className="admin-nav-label">ADMINISTRATION</p>
      <nav className="admin-nav">
        {NAVIGATION_BY_ROLE[ROLES.ADMIN].map((item) => {
          const Icon = icons[item.key];
          return <Link
            key={item.key}
            className={active === item.key ? "is-active" : ""}
            to={item.href}
          >
            <Icon aria-hidden="true" />
            {item.label}
          </Link>
        })}
      </nav>
      <SidebarProfile user={user} subtitle="Administrator" onSignOut={logout} variant="admin" />
    </aside>
  );
}
