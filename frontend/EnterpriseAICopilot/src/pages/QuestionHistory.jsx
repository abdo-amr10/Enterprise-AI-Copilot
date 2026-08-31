import { useState } from "react";
import AppSidebar from "../components/AppSidebar";
import AppTopBar from "../components/AppTopBar";
import "../styles/history.css";
const rows = [
  ["req-990", "Show me the total revenue", "Completed", "Today, 10:24 AM"],
  [
    "req-991",
    "Show customers with inactive status",
    "Completed",
    "Yesterday, 3:18 PM",
  ],
  ["req-992", "Update customer records", "Failed", "Aug 24, 11:06 AM"],
];
export default function QuestionHistory() {
  const [state, setState] = useState("list");
  return (
    <main className="copilot-shell">
      <AppSidebar active="history" />
      <section className="copilot-main history-page">
        <AppTopBar title="Question History" />
        <div className="history-actions">
          <p>Review your previous Copilot questions and results.</p>
          <div>
            {["list", "empty", "loading", "error"].map((x) => (
              <button onClick={() => setState(x)}>{x}</button>
            ))}
          </div>
        </div>
        {state === "loading" ? (
          <div className="history-center">Loading your questions…</div>
        ) : state === "empty" ? (
          <div className="history-center">
            <h2>No questions yet</h2>
            <p>Your Copilot questions will appear here.</p>
            <a href="/copilot">Ask your first question</a>
          </div>
        ) : state === "error" ? (
          <div className="history-center">
            <h2>We couldn’t load your history</h2>
            <p>Please try again in a moment.</p>
            <button onClick={() => setState("list")}>Try again</button>
          </div>
        ) : (
          <div className="history-list">
            {rows.map((r) => (
              <a href={`/history/${r[0]}`} className="history-row">
                <div>
                  <strong>{r[1]}</strong>
                  <small>
                    {r[3]} · {r[0]}
                  </small>
                </div>
                <span className={r[2] === "Completed" ? "ok" : "bad"}>
                  {r[2]}
                </span>
                <b>›</b>
              </a>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
