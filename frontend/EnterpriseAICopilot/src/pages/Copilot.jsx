import { useState, useRef, useEffect } from "react";
import AppShell from "../components/AppShell";
import ChatQuestion from "../components/ChatQuestion";
import ConversationFeedback from "../components/ConversationFeedback";
import SummaryCard from "../components/SummaryCard";
import { IconLoader, IconSend, IconSparkles } from "../components/icons";
import { useAuth } from "../context/useAuth";
import { askCopilot } from "../services/copilotService";
import "../styles/copilot.css";

const suggestions = [
  "Show monthly revenue by branch",
  "Which customers are currently inactive?",
  "Compare this quarter to the previous one",
];

function timeNow() {
  return new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Copilot() {
  const { user } = useAuth();
  const [turns, setTurns] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const conversationRef = useRef([]);
  const threadEndRef = useRef(null);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]); // [{ role, content }], resent to the backend each turn for context

  const ask = async (value = question) => {
    const nextQuestion = value.trim();
    if (!nextQuestion || sending) return;

    const turnId = `turn-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setQuestion("");
    setSending(true);
    setTurns((prev) => [
      ...prev,
      { id: turnId, question: nextQuestion, status: "processing" },
    ]);

    try {
      const response = await askCopilot({
        question: nextQuestion,
        conversation: conversationRef.current,
      });

      const askedAt = timeNow();

      if (response?.status === "Failed") {
        const errorMessage =
          response.message || "I couldn’t complete that request.";
        conversationRef.current = [
          ...conversationRef.current,
          { role: "user", content: nextQuestion },
          { role: "assistant", content: errorMessage },
        ];
        setTurns((prev) =>
          prev.map((turn) =>
            turn.id === turnId
              ? {
                  ...turn,
                  status: "failed",
                  errorMessage,
                  queryId: response.queryId,
                  askedAt,
                }
              : turn,
          ),
        );
        return;
      }

      const report = response?.report || {};
      conversationRef.current = [
        ...conversationRef.current,
        { role: "user", content: nextQuestion },
        { role: "assistant", content: report.textSummary || "" },
      ];
      setTurns((prev) =>
        prev.map((turn) =>
          turn.id === turnId
            ? {
                ...turn,
                status: "completed",
                report,
                queryId: response?.queryId,
                askedAt,
              }
            : turn,
        ),
      );
    } catch (err) {
      setTurns((prev) =>
        prev.map((turn) =>
          turn.id === turnId
            ? {
                ...turn,
                status: "failed",
                errorMessage:
                  err.message || "Something went wrong. Please try again.",
              }
            : turn,
        ),
      );
    } finally {
      setSending(false);
    }
  };

  const startNewConversation = () => {
    conversationRef.current = [];
    setQuestion("");
    setTurns([]);
  };

  const isEmpty = turns.length === 0;

  return (
    <AppShell active="copilot" title="Ask your data">
      <div className={`copilot-workspace${isEmpty ? "" : " has-thread"}`}>
        {isEmpty ? (
          <section className="copilot-empty-state">
            <span className="copilot-empty-icon">
              <IconSparkles aria-hidden="true" />
            </span>
            <p className="copilot-kicker">Enterprise intelligence</p>
            <h2>What would you like to know?</h2>
            <p>
              Ask a question in plain language and Copilot will help you
              understand your business information.
            </p>
            <div className="copilot-suggestions">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => ask(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </section>
        ) : (
          <section className="copilot-thread" aria-live="polite">
            {turns.map((turn) => (
              <div key={turn.id} className="copilot-turn">
              <div key={turn.id} className="copilot-turn">
                <ChatQuestion isAdmin={user?.role === "admin"}>
                  {turn.question}
                </ChatQuestion>

                {turn.status === "processing" ? (
                  <article className="copilot-processing-message">
                    <div className="copilot-processing-head">
                      <span>
                        <IconSparkles aria-hidden="true" /> Copilot is working
                      </span>
                      <IconLoader
                        className="copilot-processing-loader"
                        aria-hidden="true"
                      />
                    </div>
                    <p>Reviewing your question and preparing a clear answer.</p>
                  </article>
                ) : null}

                {turn.status === "completed" ? (
                  <SummaryCard
                    question={turn.question}
                    textSummary={turn.report?.textSummary}
                    data={turn.report?.data}
                    status="Completed"
                    queryId={turn.queryId}
                    askedAt={turn.askedAt}
                  />
                ) : null}

                {turn.status === "failed" ? (
                  <ConversationFeedback title="I couldn’t complete that request.">
                    {turn.errorMessage}
                  </ConversationFeedback>
                ) : null}
              </div>
            </div>
  ))}

  <div ref={threadEndRef} />
          </section>
        )}
      </div>

      <form
        className="copilot-composer"
        onSubmit={(event) => {
          event.preventDefault();
          ask();
        }}
      >
        <input
          aria-label="Ask a question"
          placeholder="Ask a question about your business..."
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={sending}
        />
        <button type="submit" aria-label="Send question" disabled={sending}>
          <IconSend aria-hidden="true" />
        </button>
      </form>

      <p className="copilot-security-note">
        Your questions are handled within your secure workspace.
      </p>

      {!isEmpty ? (
        <button
          className="copilot-new-question"
          type="button"
          onClick={startNewConversation}
          disabled={sending}
        >
          Start a new conversation
        </button>
      ) : null}
    </AppShell>
  );
}
