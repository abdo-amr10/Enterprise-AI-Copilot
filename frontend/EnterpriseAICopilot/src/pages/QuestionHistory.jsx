import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/AppShell";
import ConfirmDialog from "../components/ConfirmDialog";
import { IconLoader, IconSparkles, IconTrash } from "../components/icons";
import { deleteConversation, fetchConversations } from "../services/copilotService";
import { useAuth } from "../context/useAuth";
import { formatHistoryDate } from "../utils/formatDate";
import "../styles/history.css";

export default function QuestionHistory() {
  const { user } = useAuth();
  const [state, setState] = useState("loading");
  const [items, setItems] = useState([]);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const activeKey = `enterprise-ai-copilot-active-conversation:${user?.userId || user?.email || "current"}`;

  const load = async () => {
    setState("loading");
    try {
      const response = await fetchConversations();
      const conversations = Array.isArray(response) ? response : response?.items || response?.conversations || [];
      setItems(conversations);
      setState(conversations.length ? "list" : "empty");
    } catch {
      setState("error");
    }
  };

  useEffect(() => { Promise.resolve().then(load); }, []);

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteConversation(pendingDelete.conversationId);
      setItems((current) => {
        const next = current.filter((item) => item.conversationId !== pendingDelete.conversationId);
        setState(next.length ? "list" : "empty");
        return next;
      });
      try {
        const saved = JSON.parse(sessionStorage.getItem(activeKey) || "null");
        const savedId = typeof saved === "string" ? saved : saved?.conversationId;
        if (savedId === pendingDelete.conversationId) sessionStorage.removeItem(activeKey);
      } catch {
        // A malformed cached value should not block the server deletion.
        sessionStorage.removeItem(activeKey);
      }
      setPendingDelete(null);
    } catch {
      setDeleteError("We couldn’t delete this conversation. Please try again.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <AppShell active="history" title="Conversation History" mainClassName="history-page">
      <div className="history-actions"><p>Review and continue your previous Copilot conversations.</p></div>
      {state === "loading" ? <div className="history-state history-loading"><div className="history-state-icon loading-icon"><IconLoader aria-hidden="true" /></div><span className="history-state-kicker">Please wait</span><h2>Loading your conversations</h2><p>We’re retrieving your previous Copilot conversations.</p><div className="history-loading-bar"><span /></div></div> : null}
      {state === "empty" ? <div className="history-state history-empty"><div className="history-state-icon"><IconSparkles aria-hidden="true" /></div><span className="history-state-kicker">My Conversations</span><h2>No conversations yet</h2><p>Your Copilot conversations will appear here once you start asking.</p><Link className="history-primary-action" to="/copilot">Start a conversation <span aria-hidden="true">→</span></Link></div> : null}
      {state === "error" ? <div className="history-state history-error"><div className="history-state-icon error-icon"><span aria-hidden="true">!</span></div><span className="history-state-kicker">Something went wrong</span><h2>We couldn’t load your conversations</h2><p>Please try again in a moment.</p><button className="history-primary-action" type="button" onClick={load}>Try again</button></div> : null}
      {deleteError ? <p className="history-delete-error" role="alert">{deleteError}</p> : null}
      {state === "list" ? <div className="history-list">{items.map((item) => <article key={item.conversationId} className="history-row"><Link to={`/history/${item.conversationId}`} className="history-row-link"><div><strong>{item.title || item.lastQuestion || "Copilot conversation"}</strong><small>{item.lastQuestion || "No questions yet"}<br />Updated {formatHistoryDate(item.updatedAt || item.createdAt)}</small></div><span className="ok">Conversation</span><b aria-hidden="true">›</b></Link><button className="history-delete" type="button" aria-label={`Delete ${item.title || "conversation"}`} onClick={() => { setDeleteError(""); setPendingDelete(item); }}><IconTrash aria-hidden="true" /></button></article>)}</div> : null}
      <ConfirmDialog open={Boolean(pendingDelete)} title="Delete conversation?" message="This conversation and its messages will be permanently removed." confirmLabel="Delete conversation" variant="destructive" isBusy={deleting} onConfirm={confirmDelete} onCancel={() => !deleting && setPendingDelete(null)} />
    </AppShell>
  );
}
