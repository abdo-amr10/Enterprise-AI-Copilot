
import { useEffect, useState } from "react";
import AdminSidebar from "../components/AdminSidebar";
import AdminTopBar from "../components/AdminTopBar";
import { IconAlertCircle, IconLoader, IconShieldCheck } from "../components/icons";
import { fetchAuditLogs } from "../services/auditService";
import { fetchUsers } from "../services/adminUsersService";
import "../styles/admin.css";
import "../styles/admin-pages.css";

const emptyFilters = { action: "", from: "", to: "", userId: "" };

const toIsoStart = (date) => (date ? `${date}T00:00:00Z` : "");
const toIsoEnd = (date) => (date ? `${date}T23:59:59Z` : "");

function formatTimestamp(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function usersFromResponse(response) {
  if (Array.isArray(response)) return response;
  const data = response?.items || response?.users || response?.data || response;
  return Array.isArray(data) ? data : data?.items || data?.users || [];
}

function userDisplayName(user) {
  return [user?.firstName, user?.lastName].filter(Boolean).join(" ") || user?.name || user?.fullName || "—";
}

function auditUserDetails(item, usersById) {
  const directoryUser = usersById[String(item.userId || "").toLowerCase()];
  return {
    name: userDisplayName(directoryUser) !== "—" ? userDisplayName(directoryUser) : item.userName || item.user?.fullName || item.user?.name || item.userId || "—",
    email: directoryUser?.email || item.userEmail || item.email || item.user?.email || "—",
  };
}

export default function AdminAuditLogs() {
  const [state, setState] = useState("loading"); // loading | list | empty | error
  const [items, setItems] = useState([]);
  const [usersById, setUsersById] = useState({});
  const [filters, setFilters] = useState(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState(emptyFilters);

  const load = async (activeFilters) => {
    setState("loading");
    try {
      const [auditResult, usersResult] = await Promise.allSettled([fetchAuditLogs({
        action: activeFilters.action || undefined,
        from: toIsoStart(activeFilters.from) || undefined,
        to: toIsoEnd(activeFilters.to) || undefined,
        userId: activeFilters.userId || undefined,
      }), fetchUsers()]);
      if (auditResult.status === "rejected") throw auditResult.reason;
      const response = auditResult.value;
      const list = Array.isArray(response) ? response : response?.items || [];
      const directory = usersResult.status === "fulfilled" ? usersFromResponse(usersResult.value) : [];
      setUsersById(Object.fromEntries(directory.filter((user) => user?.userId).map((user) => [String(user.userId).toLowerCase(), user])));
      setItems(list);
      setState(list.length > 0 ? "list" : "empty");
    } catch {
      setState("error");
    }
  };

  useEffect(() => {
    Promise.resolve().then(() => load(emptyFilters));
  }, []);

  const onApply = (event) => {
    event.preventDefault();
    setAppliedFilters(filters);
    load(filters);
  };

  const onReset = () => {
    setFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
    load(emptyFilters);
  };

  const hasActiveFilters = Object.values(appliedFilters).some(Boolean);

  const update = (key) => (event) => setFilters((current) => ({ ...current, [key]: event.target.value }));

  return (
    <main className="admin-shell">
      <AdminSidebar active="audit" />
      <section className="admin-main audit-main">
        <AdminTopBar
          title="Audit Logs"
          description="Review immutable activity for security and operational oversight."
        />

        <form className="audit-filters" onSubmit={onApply}>
          <label>
            Action
            <input placeholder="e.g. QueryExecution" value={filters.action} onChange={update("action")} />
          </label>
          <label>
            From
            <input type="date" value={filters.from} onChange={update("from")} />
          </label>
          <label>
            To
            <input type="date" value={filters.to} onChange={update("to")} />
          </label>
          <label>
            User ID
            <input placeholder="e.g. usr-123" value={filters.userId} onChange={update("userId")} />
          </label>
          <button type="submit" className="primary">
            Apply
          </button>
          <button type="button" className="secondary" onClick={onReset}>
            Reset
          </button>
        </form>

        {state === "loading" ? (
          <div className="audit-table-scroll">
            <div className="admin-state">
              <div className="admin-state-icon">
                <IconLoader className="is-spinning" aria-hidden="true" />
              </div>
              <span className="admin-state-kicker">Please wait</span>
              <h2>Loading audit activity</h2>
              <p>We’re retrieving the latest security and operational events.</p>
              <div className="admin-state-loading-bar">
                <span />
              </div>
            </div>
          </div>
        ) : state === "error" ? (
          <div className="audit-table-scroll">
            <div className="admin-state is-error">
              <div className="admin-state-icon">
                <IconAlertCircle aria-hidden="true" />
              </div>
              <span className="admin-state-kicker">Something went wrong</span>
              <h2>Audit logs are unavailable</h2>
              <p>We couldn’t retrieve audit activity right now. Please try again in a moment.</p>
              <button className="admin-state-action" type="button" onClick={() => load(appliedFilters)}>
                Try again
              </button>
            </div>
          </div>
        ) : state === "empty" ? (
          <div className="audit-table-scroll">
            <div className="admin-state">
              <div className="admin-state-icon">
                <IconShieldCheck aria-hidden="true" />
              </div>
              <span className="admin-state-kicker">Audit Logs</span>
              <h2>{hasActiveFilters ? "No events match your filters" : "No audit activity yet"}</h2>
              <p>
                {hasActiveFilters
                  ? "Try widening your date range or clearing some filters."
                  : "Security and operational events will appear here as they happen."}
              </p>
              {hasActiveFilters ? (
                <button className="admin-state-action" type="button" onClick={onReset}>
                  Clear filters
                </button>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="audit-table-scroll">
            <div className="admin-table">
              <div className="table-row audit table-head">
                <span>Action</span>
                <span>User</span>
                <span>Status</span>
                <span>Time</span>
              </div>
              {items.map((item) => {
                const auditUser = auditUserDetails(item, usersById);
                return <div className="table-row audit" key={item.eventId}>
                  <span>
                    <b>{item.action}</b>
                    <small>{item.eventId}</small>
                  </span>
                  <span><b>{auditUser.name}</b><small>{auditUser.email}</small></span>
                  <span className={`admin-badge${item.status === "Success" ? "" : " is-failed"}`}>
                    {item.status}
                  </span>
                  <span>{formatTimestamp(item.timestamp)}</span>
                </div>;
              })}
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
