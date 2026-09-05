
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AppShell from "../components/AppShell";
import ChatQuestion from "../components/ChatQuestion";
import ConversationFeedback from "../components/ConversationFeedback";
import SummaryCard from "../components/SummaryCard";
import { IconArrowLeft, IconLoader } from "../components/icons";
import { fetchHistoryItem } from "../services/historyService";
import { formatHistoryDate } from "../utils/formatDate";
import "../styles/history.css";

export default function QuestionDetails() {
  const { queryId } = useParams();
  const [state, setState] = useState("loading"); // loading | success | failed | unavailable | error
  const [item, setItem] = useState(null);

  

  const load = useCallback(() => {
    setState("loading");
    fetchHistoryItem(queryId)
  .then((response) => {
    console.log("RESULT:", response.result);
    console.log("FULL RESPONSE:", response);

    if (!response) {
      setState("unavailable");
      return;
    }
        setItem(response);
        setState(response.status === "Failed" ? "failed" : "success");
      })
      .catch((err) => {
        setState(err.status === 404 ? "unavailable" : "error");
      });
  }, [queryId]);

  useEffect(() => {
    Promise.resolve().then(load);
  }, [load]);

  const body =
    state === "loading" ? (
      <div className="history-state history-loading">
        <div className="history-state-icon loading-icon">
          <IconLoader aria-hidden="true" />
        </div>
        <span className="history-state-kicker">Please wait</span>
        <h2>Loading this question</h2>
        <p>We’re retrieving the question and its result.</p>
      </div>
    ) : state === "success" ? (
      <>
        <ChatQuestion>{item.question}</ChatQuestion>
        <SummaryCard
          question={item.question}
          textSummary={item.result?.textSummary}
          data={item.result?.data}
          status={item.status}
          queryId={item.queryId}
          askedAt={formatHistoryDate(item.createdAt)}
        />
      </>
    ) : state === "failed" ? (
      <>
        <ChatQuestion>{item?.question}</ChatQuestion>
        <ConversationFeedback title="We couldn’t complete this question.">
          {item?.message || "This question could not be completed."}
        </ConversationFeedback>
      </>
    ) : state === "error" ? (
      <div className="history-state history-error">
        <div className="history-state-icon error-icon">
          <span aria-hidden="true">!</span>
        </div>
        <span className="history-state-kicker">Something went wrong</span>
        <h2>We couldn’t load this question</h2>
        <p>Please try again in a moment.</p>
        <button className="history-primary-action" type="button" onClick={load}>
          Try again
        </button>
      </div>
    ) : (
      <ConversationFeedback title="This question is unavailable.">
        You no longer have access to view this question or its result.
      </ConversationFeedback>
    );

  return (
    <AppShell active="history" title="Question Details" mainClassName="question-details-main">
      <Link className="back" to="/history">
        <IconArrowLeft aria-hidden="true" />
        Back to history
      </Link>

      <div className="chat-thread">{body}</div>
    </AppShell>
  );
}
