import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AppShell from "../components/AppShell";
import ConversationFeedback from "../components/ConversationFeedback";
import { CopilotComposer, CopilotThread } from "../components/CopilotConversation";
import { IconArrowLeft, IconLoader } from "../components/icons";
import { useAuth } from "../context/useAuth";
import { askCopilot, fetchConversation, getConversationMessages } from "../services/copilotService";
import { toTurns } from "../utils/copilotTurns";
import "../styles/history.css";
import "../styles/copilot.css";

function toConversationContext(messages) {
  const context = [];
  messages.forEach((message) => {
    const messageRole = String(message?.role || message?.sender || "").toLowerCase();
    const question = message?.question || (messageRole === "user" ? message?.content : "");
    const result = message?.result || message?.report;
    const summary = result?.textSummary || message?.answer || message?.content;

    if (question) context.push({ role: "user", content: question });
    if (summary && (result || messageRole === "assistant")) context.push({ role: "assistant", content: summary });
  });
  return context;
}

export default function QuestionDetails() {
  const { conversationId } = useParams();
  const { user } = useAuth();
  const [state, setState] = useState("loading");
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const conversationRef = useRef([]);
  const [turns, setTurns] = useState([]);

  const load = useCallback(() => {
    setState("loading");
    fetchConversation(conversationId)
      .then((response) => {
        if (!response) { setState("unavailable"); return; }
        const restoredMessages = getConversationMessages(response);
        conversationRef.current = toConversationContext(restoredMessages);
        setTurns(toTurns(restoredMessages));
        setState("success");
      })
      .catch((error) => setState(error.status === 404 ? "unavailable" : "error"));
  }, [conversationId]);

  useEffect(() => { Promise.resolve().then(load); }, [load]);
  const ask = async (value = question) => {
    const nextQuestion = value.trim();
    if (!nextQuestion || sending || state !== "success") return;

    const turnId = `turn-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setQuestion("");
    setSending(true);
    setTurns((current) => [...current, { id: turnId, question: nextQuestion, status: "processing" }]);
    try {
      const response = await askCopilot({
        question: nextQuestion,
        conversationId,
        conversation: conversationRef.current,
      });
      const report = response?.report || response?.result || {};
      const status = response?.status === "Failed" ? "Failed" : "Completed";
      const errorMessage = response?.errorMessage || response?.message || "This question could not be completed.";
      conversationRef.current = [
        ...conversationRef.current,
        { role: "user", content: nextQuestion },
        { role: "assistant", content: report.textSummary || (status === "Failed" ? errorMessage : "Query completed.") },
      ];
      setTurns((current) => current.map((turn) => turn.id === turnId ? {
        ...turn,
        status: status === "Failed" ? "failed" : "completed",
        report,
        queryId: response?.queryId,
        executionTimeMs: response?.executionTimeMs,
        errorMessage,
        askedAt: new Date().toISOString(),
      } : turn));
    } catch (error) {
      setTurns((current) => current.map((turn) => turn.id === turnId ? {
        ...turn,
        status: "failed",
        errorMessage: error.message || "Something went wrong. Please try again.",
      } : turn));
    } finally {
      setSending(false);
    }
  };

  return (
    <AppShell active="history" title="Conversation Details" mainClassName="question-details-main">
      <Link className="back question-details-back" to="/history"><IconArrowLeft aria-hidden="true" />Back to conversations</Link>
      <div className="question-details-content">
        {state === "loading" ? <div className="history-state history-loading"><div className="history-state-icon loading-icon"><IconLoader aria-hidden="true" /></div><span className="history-state-kicker">Please wait</span><h2>Loading this conversation</h2><p>We’re retrieving all questions and answers.</p></div> : null}
        {state === "success" && turns.length ? <CopilotThread turns={turns} role={user?.role} /> : null}
        {state === "success" && !turns.length ? <ConversationFeedback title="This conversation has no messages yet.">Start a new question in Copilot to continue it.</ConversationFeedback> : null}
        {state === "error" ? <div className="history-state history-error"><div className="history-state-icon error-icon"><span aria-hidden="true">!</span></div><span className="history-state-kicker">Something went wrong</span><h2>We couldn’t load this conversation</h2><p>Please try again in a moment.</p><button className="history-primary-action" type="button" onClick={load}>Try again</button></div> : null}
        {state === "unavailable" ? <ConversationFeedback title="This conversation is unavailable.">You no longer have access to this conversation.</ConversationFeedback> : null}
      </div>
      {state === "success" ? <CopilotComposer question={question} setQuestion={setQuestion} onSubmit={ask} sending={sending} /> : null}
      {state === "success" ? <p className="copilot-security-note">Your questions are handled within your secure workspace.</p> : null}
    </AppShell>
  );
}
