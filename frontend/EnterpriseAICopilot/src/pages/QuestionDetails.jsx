import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AppShell from "../components/AppShell";
import ChatQuestion from "../components/ChatQuestion";
import ConversationFeedback from "../components/ConversationFeedback";
import SummaryCard from "../components/SummaryCard";
import { IconArrowLeft, IconLoader } from "../components/icons";
import { useAuth } from "../context/useAuth";
import { fetchConversation, getConversationMessages } from "../services/copilotService";
import { formatHistoryDate } from "../utils/formatDate";
import "../styles/history.css";

function ConversationMessages({ messages, role }) {
  return messages.map((message, index) => {
    const messageRole = String(message?.role || message?.sender || "").toLowerCase();
    const question = message?.question || (messageRole === "user" ? message?.content : "");
    if (question) {
      const status = String(message?.status || "").toLowerCase();
      const result = message?.result || message?.report;
      return <div key={message?.id || message?.messageId || message?.queryId || index}><ChatQuestion role={role}>{question}</ChatQuestion>{status === "failed" ? <ConversationFeedback title="I couldn’t complete that request.">{message?.message || "This question could not be completed."}</ConversationFeedback> : <SummaryCard question={question} textSummary={result?.textSummary} data={result?.data} heroMetric={result?.heroMetric} kpiCards={result?.kpiCards} status={message?.status || "Completed"} queryId={message?.queryId} executionTimeMs={message?.executionTimeMs} askedAt={formatHistoryDate(message?.createdAt)} />}</div>;
    }

    const result = message?.result || message?.report;
    if (result) return <SummaryCard key={message?.id || message?.messageId || index} question={message?.question} textSummary={result?.textSummary} data={result?.data} heroMetric={result?.heroMetric} kpiCards={result?.kpiCards} status={message?.status || "Completed"} queryId={message?.queryId} executionTimeMs={message?.executionTimeMs} askedAt={formatHistoryDate(message?.createdAt)} />;
    return <ConversationFeedback key={message?.id || message?.messageId || index} title={message?.status === "Failed" ? "I couldn’t complete that request." : "Copilot"}>{message?.content || message?.answer || message?.message || "No response was returned."}</ConversationFeedback>;
  });
}

export default function QuestionDetails() {
  const { conversationId } = useParams();
  const { user } = useAuth();
  const [state, setState] = useState("loading");
  const [conversation, setConversation] = useState(null);

  const load = useCallback(() => {
    setState("loading");
    fetchConversation(conversationId)
      .then((response) => {
        if (!response) { setState("unavailable"); return; }
        setConversation(response);
        setState("success");
      })
      .catch((error) => setState(error.status === 404 ? "unavailable" : "error"));
  }, [conversationId]);

  useEffect(() => { Promise.resolve().then(load); }, [load]);
  const messages = getConversationMessages(conversation);

  return (
    <AppShell active="history" title="Conversation Details" mainClassName="question-details-main">
      <Link className="back question-details-back" to="/history"><IconArrowLeft aria-hidden="true" />Back to conversations</Link>
      <div className="question-details-content">
        <div className="chat-thread">
          {state === "loading" ? <div className="history-state history-loading"><div className="history-state-icon loading-icon"><IconLoader aria-hidden="true" /></div><span className="history-state-kicker">Please wait</span><h2>Loading this conversation</h2><p>We’re retrieving all questions and answers.</p></div> : null}
          {state === "success" && messages.length ? <ConversationMessages messages={messages} role={user?.role} /> : null}
          {state === "success" && !messages.length ? <ConversationFeedback title="This conversation has no messages yet.">Start a new question in Copilot to continue it.</ConversationFeedback> : null}
          {state === "error" ? <div className="history-state history-error"><div className="history-state-icon error-icon"><span aria-hidden="true">!</span></div><span className="history-state-kicker">Something went wrong</span><h2>We couldn’t load this conversation</h2><p>Please try again in a moment.</p><button className="history-primary-action" type="button" onClick={load}>Try again</button></div> : null}
          {state === "unavailable" ? <ConversationFeedback title="This conversation is unavailable.">You no longer have access to this conversation.</ConversationFeedback> : null}
        </div>
      </div>
    </AppShell>
  );
}
