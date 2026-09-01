

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/AppShell";
import { IconLoader, IconSparkles } from "../components/icons";
import { fetchHistory } from "../services/historyService";
import { formatHistoryDate } from "../utils/formatDate";
import "../styles/history.css";

export default function QuestionHistory() {
  const [state, setState] = useState("loading"); // loading | list | empty | error
  const [items, setItems] = useState([]);

  const load = async () => {
    setState("loading");
    try {
      const response = await fetchHistory();
      const list = response?.items || [];
      setItems(list);
      setState(list.length > 0 ? "list" : "empty");
    } catch {
      setState("error");
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <AppShell active="history" title="Question History" mainClassName="history-page">
      <div className="history-actions">
        <p>Review your previous Copilot questions and results.</p>
      </div>

      {state === "loading" ? (
        <div className="history-state history-loading">
          <div className="history-state-icon loading-icon">
            <IconLoader aria-hidden="true" />
          </div>

          <span className="history-state-kicker">Please wait</span>

          <h2>Loading your questions</h2>

          <p>We’re retrieving your previous questions and results.</p>

          <div className="history-loading-bar">
            <span />
          </div>
        </div>
      ) : state === "empty" ? (
        <div className="history-state history-empty">
          <div className="history-state-icon">
            <IconSparkles aria-hidden="true" />
          </div>

          <span className="history-state-kicker">My Questions</span>

          <h2>No questions yet</h2>

          <p>Your Copilot questions and results will appear here once you start asking.</p>

          <Link className="history-primary-action" to="/copilot">
            Ask your first question
            <span aria-hidden="true">→</span>
          </Link>
        </div>
      ) : state === "error" ? (
        <div className="history-state history-error">
          <div className="history-state-icon error-icon">
            <span aria-hidden="true">!</span>
          </div>

          <span className="history-state-kicker">Something went wrong</span>

          <h2>We couldn’t load your history</h2>

          <p>We couldn’t retrieve your previous questions right now. Please try again in a moment.</p>

          <button className="history-primary-action" type="button" onClick={load}>
            Try again
          </button>
        </div>
      ) : (
        <div className="history-list">
          {items.map((item) => (
            <Link key={item.queryId} to={`/history/${item.queryId}`} className="history-row">
              <div>
                <strong>{item.question}</strong>
                <small>
                  {formatHistoryDate(item.createdAt)} · {item.queryId}
                </small>
              </div>

              <span className={item.status === "Completed" ? "ok" : "bad"}>{item.status}</span>

              <b>›</b>
            </Link>
          ))}
        </div>
      )}
    </AppShell>
  );
}
