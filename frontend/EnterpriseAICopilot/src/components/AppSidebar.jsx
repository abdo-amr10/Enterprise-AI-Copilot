import { Link } from "react-router-dom";
import Logo from "../assets/Logo.png";
import { NAVIGATION_BY_ROLE } from "../config/routes";
import { ROLES } from "../config/roles";
import { useAuth } from "../context/useAuth";
import { IconHistory, IconSparkles } from "./icons";
import SidebarProfile from './SidebarProfile'

const icons = { copilot: IconSparkles, history: IconHistory };

export default function AppSidebar({ active }) {
  const { logout, user } = useAuth();

  return (
    <aside className="copilot-sidebar">
      <Link className="copilot-logo" to="/copilot">
        <img src={Logo} alt="" />
        <span>
          Enterprise
          <br />
          <b>AI</b> Copilot
        </span>
      </Link>
      <nav className="copilot-nav">
        {NAVIGATION_BY_ROLE[ROLES.NORMAL].map((item) => {
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
      <SidebarProfile user={user} subtitle="Secure workspace" onSignOut={logout} />
    </aside>
  );
}
