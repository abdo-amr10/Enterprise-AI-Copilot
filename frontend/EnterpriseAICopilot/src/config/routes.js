import { ROLES } from "./roles";

export const HOME_BY_ROLE = Object.freeze({
  [ROLES.NORMAL]: "/copilot",
  [ROLES.ADMIN]: "/admin",
});

export const NAVIGATION_BY_ROLE = Object.freeze({
  [ROLES.NORMAL]: [
    { key: "copilot", href: "/copilot", label: "Copilot" },
    { key: "history", href: "/history", label: "Question History" },
  ],
  [ROLES.ADMIN]: [
    { key: "copilot", href: "/copilot", label: "Copilot" },
    { key: "history", href: "/history", label: "Question History" },
    { key: "dashboard", href: "/admin", label: "Dashboard" },
    { key: "semantic", href: "/admin/semantic-layers", label: "Semantic Layers" },
    { key: "users", href: "/admin/users", label: "Users" },
    { key: "audit", href: "/admin/audit-logs", label: "Audit Logs" },
  ],
});

export const ROLE_PATHS = Object.freeze({
  [ROLES.NORMAL]: ["/copilot", "/history"],
  [ROLES.ADMIN]: [
    "/copilot",
    "/history",
    "/admin",
    "/admin/semantic-layer",
    "/admin/semantic-layer/upload",
    "/admin/semantic-layers",
    "/admin/semantic-layers/:layerId",
    "/admin/review",
    "/admin/users",
    "/admin/audit-logs",
  ],
});
