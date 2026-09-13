import { useEffect, useRef, useState } from "react";
import AppShell from "../components/AppShell";
import { CopilotComposer, CopilotThread } from "../components/CopilotConversation";
import { IconSparkles } from "../components/icons";
import { useAuth } from "../context/useAuth";
import { askCopilot, extractConversationId, fetchConversation, findConversationIdForQuestion, getConversationMessages } from "../services/copilotService";
import { toTurns } from "../utils/copilotTurns";
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
  return new Date().toISOString();
}

export default function Copilot() {
  const { user } = useAuth();
  const [turns, setTurns] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const conversationRef = useRef([]);
  const turnsRef = useRef([]);

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
        const restoredTurns = toTurns(messages);
        conversationRef.current = restoredTurns.flatMap((turn) => [
          { role: "user", content: turn.question },
          { role: "assistant", content: turn.report?.textSummary || "Query completed." },
        ]);
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
        const errorMessage = response.errorMessage || response.message || "This question could not be completed.";
        conversationRef.current = [...conversationRef.current, { role: "user", content: nextQuestion }, { role: "assistant", content: errorMessage }];
        turnsRef.current = turnsRef.current.map((turn) => turn.id === turnId ? { ...turn, status: "failed", errorMessage, queryId: response.queryId, askedAt } : turn);
        setTurns(turnsRef.current);
        saveActiveConversation(user, { conversationId: nextConversationId || conversationId, turns: turnsRef.current, conversation: conversationRef.current });
        return;
      }

      const report = response?.report || response?.result || {};
      conversationRef.current = [...conversationRef.current, { role: "user", content: nextQuestion }, { role: "assistant", content: report.textSummary || "Query completed." }];
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
        {isEmpty ? <section className="copilot-empty-state"><span className="copilot-empty-icon"><IconSparkles aria-hidden="true" /></span><p className="copilot-kicker">Enterprise intelligence</p><h2>What would you like to know?</h2><p>Ask a question in plain language and Copilot will help you understand your business information.</p><div className="copilot-suggestions">{suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => ask(suggestion)}>{suggestion}</button>)}</div></section> : <CopilotThread turns={turns} role={user?.role} />}
      </div>
      <CopilotComposer question={question} setQuestion={setQuestion} onSubmit={ask} sending={sending} />
      <p className="copilot-security-note">Your questions are handled within your secure workspace.</p>
      {!isEmpty ? <button className="copilot-new-question" type="button" onClick={startNewConversation} disabled={sending}>Start a new conversation</button> : null}
    </AppShell>
  );
}
