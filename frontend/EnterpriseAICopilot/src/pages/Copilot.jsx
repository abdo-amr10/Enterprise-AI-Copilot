import { useEffect, useRef, useState } from "react";
import AppShell from "../components/AppShell";
import ChatQuestion from "../components/ChatQuestion";
import ConversationFeedback from "../components/ConversationFeedback";
import SummaryCard from "../components/SummaryCard";
import { IconLoader, IconSend, IconSparkles } from "../components/icons";
import { useAuth } from "../context/useAuth";
import { askCopilot, extractConversationId, fetchConversation, findConversationIdForQuestion, getConversationMessages } from "../services/copilotService";
import "../styles/copilot.css";

const suggestions = [
  "Show monthly revenue by branch",
  "Which customers are currently inactive?",
  "Compare this quarter to the previous one",
];

const activeConversationKey = (user) =>
  `enterprise-ai-copilot-active-conversation:${user?.userId || user?.email || "current"}`;

function readActiveConversation(user) {
  try {
    const raw = sessionStorage.getItem(activeConversationKey(user));
    if (!raw) return null;
    let saved;
    try {
      saved = JSON.parse(raw);
    } catch {
      return { conversationId: raw, turns: [], conversation: [] };
    }
    if (typeof saved === "string") return { conversationId: saved, turns: [], conversation: [] };
    return saved && typeof saved === "object" ? saved : null;
  } catch {
    return null;
  }
}

function saveActiveConversation(user, value) {
  if (!value?.conversationId) return;
  sessionStorage.setItem(activeConversationKey(user), JSON.stringify(value));
}

function timeNow() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function toTurns(messages) {
  const turns = [];
  messages.forEach((message, index) => {
    const role = String(message?.role || message?.sender || "").toLowerCase();
    const question = message?.question || (role === "user" ? message?.content : "");
    if (question) {
      const status = String(message?.status || "").toLowerCase();
      turns.push({
        id: message?.id || message?.messageId || message?.queryId || `question-${index}`,
        question,
        status: status === "failed" ? "failed" : "completed",
        queryId: message?.queryId,
        report: message?.result || message?.report || { textSummary: "" },
        executionTimeMs: message?.executionTimeMs,
        errorMessage: message?.message || "This question could not be completed.",
        askedAt: message?.createdAt,
      });
      return;
    }
    const latestTurn = turns.at(-1);
    if (!latestTurn) return;
    const result = message?.result || message?.report;
    latestTurn.status = String(message?.status || "").toLowerCase() === "failed" ? "failed" : "completed";
    latestTurn.queryId = message?.queryId;
    latestTurn.report = result || { textSummary: message?.content || message?.answer || "" };
    latestTurn.executionTimeMs = message?.executionTimeMs;
    latestTurn.errorMessage = message?.message || message?.content;
    latestTurn.askedAt = message?.createdAt || latestTurn.askedAt;
  });
  return turns;
}

export default function Copilot() {
  const { user } = useAuth();
  const [turns, setTurns] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const conversationRef = useRef([]);
  const turnsRef = useRef([]);
  const threadEndRef = useRef(null);

  useEffect(() => {
    if (!user) return;
    const saved = readActiveConversation(user);
    if (!saved?.conversationId) return;
    const savedConversationId = saved.conversationId;
    setConversationId(savedConversationId);
    if (saved.turns?.length) {
      turnsRef.current = saved.turns;
      setTurns(saved.turns);
    }
    if (saved.conversation?.length) conversationRef.current = saved.conversation;

    Promise.resolve()
      .then(() => fetchConversation(savedConversationId))
      .then((conversation) => {
        const messages = getConversationMessages(conversation);
        setConversationId(savedConversationId);
        conversationRef.current = messages
          .map((message) => ({ role: message?.role, content: message?.content || message?.answer || message?.question }))
          .filter((message) => message.role && message.content);
        const restoredTurns = toTurns(messages);
        if (restoredTurns.length) {
          turnsRef.current = restoredTurns;
          setTurns(restoredTurns);
        }
        saveActiveConversation(user, {
          conversationId: savedConversationId,
          turns: restoredTurns.length ? restoredTurns : turnsRef.current,
          conversation: conversationRef.current,
        });
      })
      .catch(() => {
        // Keep the cached conversation. A temporary details failure must not
        // turn the next question into a new conversation.
      });
  }, [user]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const ask = async (value = question) => {
    const nextQuestion = value.trim();
    if (!nextQuestion || sending) return;

    const turnId = `turn-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setQuestion("");
    setSending(true);
    const processingTurn = { id: turnId, question: nextQuestion, status: "processing" };
    turnsRef.current = [...turnsRef.current, processingTurn];
    setTurns(turnsRef.current);

    try {
      const response = await askCopilot({ question: nextQuestion, conversationId, conversation: conversationRef.current });
      let nextConversationId = extractConversationId(response);
      if (!nextConversationId) {
        try {
          nextConversationId = await findConversationIdForQuestion(nextQuestion);
        } catch {
          // The ask result is still rendered; the cached id is retained if one exists.
        }
      }
      if (nextConversationId) {
        setConversationId(nextConversationId);
        saveActiveConversation(user, { conversationId: nextConversationId, turns: turnsRef.current, conversation: conversationRef.current });
      }

      const askedAt = timeNow();
      if (response?.status === "Failed") {
        const errorMessage = response.message || "I couldn’t complete that request.";
        conversationRef.current = [...conversationRef.current, { role: "user", content: nextQuestion }, { role: "assistant", content: errorMessage }];
        turnsRef.current = turnsRef.current.map((turn) => turn.id === turnId ? { ...turn, status: "failed", errorMessage, queryId: response.queryId, askedAt } : turn);
        setTurns(turnsRef.current);
        saveActiveConversation(user, { conversationId: nextConversationId || conversationId, turns: turnsRef.current, conversation: conversationRef.current });
        return;
      }

      const report = response?.report || response?.result || {};
      conversationRef.current = [...conversationRef.current, { role: "user", content: nextQuestion }, { role: "assistant", content: report.textSummary || "" }];
      turnsRef.current = turnsRef.current.map((turn) => turn.id === turnId ? { ...turn, status: "completed", report, queryId: response?.queryId, executionTimeMs: response?.executionTimeMs, askedAt } : turn);
      setTurns(turnsRef.current);
      saveActiveConversation(user, { conversationId: nextConversationId || conversationId, turns: turnsRef.current, conversation: conversationRef.current });
    } catch (error) {
      const failedConversationId = extractConversationId(error.payload);
      if (failedConversationId) {
        setConversationId(failedConversationId);
        saveActiveConversation(user, { conversationId: failedConversationId, turns: turnsRef.current, conversation: conversationRef.current });
      }
      turnsRef.current = turnsRef.current.map((turn) => turn.id === turnId ? { ...turn, status: "failed", errorMessage: error.message || "Something went wrong. Please try again." } : turn);
      setTurns(turnsRef.current);
    } finally {
      setSending(false);
    }
  };

  const startNewConversation = () => {
    conversationRef.current = [];
    turnsRef.current = [];
    setConversationId(null);
    sessionStorage.removeItem(activeConversationKey(user));
    setQuestion("");
    setTurns([]);
  };

  const isEmpty = turns.length === 0;

  return (
    <AppShell active="copilot" title="Ask your data">
      <div className={`copilot-workspace${isEmpty ? "" : " has-thread"}`}>
        {isEmpty ? <section className="copilot-empty-state"><span className="copilot-empty-icon"><IconSparkles aria-hidden="true" /></span><p className="copilot-kicker">Enterprise intelligence</p><h2>What would you like to know?</h2><p>Ask a question in plain language and Copilot will help you understand your business information.</p><div className="copilot-suggestions">{suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => ask(suggestion)}>{suggestion}</button>)}</div></section> : <section className="copilot-thread" aria-live="polite">{turns.map((turn) => <div key={turn.id} className="copilot-turn"><ChatQuestion role={user?.role}>{turn.question}</ChatQuestion>{turn.status === "processing" ? <article className="copilot-processing-message"><div className="copilot-processing-head"><span><IconSparkles aria-hidden="true" /> Copilot is working</span><IconLoader className="copilot-processing-loader" aria-hidden="true" /></div><p>Reviewing your question and preparing a clear answer.</p></article> : null}{turn.status === "completed" ? <SummaryCard question={turn.question} textSummary={turn.report?.textSummary} data={turn.report?.data} heroMetric={turn.report?.heroMetric} kpiCards={turn.report?.kpiCards} status="Completed" queryId={turn.queryId} executionTimeMs={turn.executionTimeMs} askedAt={turn.askedAt} /> : null}{turn.status === "failed" ? <ConversationFeedback title="I couldn’t complete that request.">{turn.errorMessage}</ConversationFeedback> : null}</div>)}<div ref={threadEndRef} /></section>}
      </div>
      <form className="copilot-composer" onSubmit={(event) => { event.preventDefault(); ask(); }}><input aria-label="Ask a question" placeholder="Ask a question about your business..." value={question} onChange={(event) => setQuestion(event.target.value)} disabled={sending} /><button type="submit" aria-label="Send question" disabled={sending}><IconSend aria-hidden="true" /></button></form>
      <p className="copilot-security-note">Your questions are handled within your secure workspace.</p>
      {!isEmpty ? <button className="copilot-new-question" type="button" onClick={startNewConversation} disabled={sending}>Start a new conversation</button> : null}
    </AppShell>
  );
}
