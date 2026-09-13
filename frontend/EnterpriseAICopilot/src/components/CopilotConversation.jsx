import { useEffect, useRef } from "react";
import ChatQuestion from "./ChatQuestion";
import ConversationFeedback from "./ConversationFeedback";
import SummaryCard from "./SummaryCard";
import { IconLoader, IconSend, IconSparkles } from "./icons";

export function CopilotThread({ turns, role }) {
  const threadEndRef = useRef(null);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  return <section className="copilot-thread" aria-live="polite">{turns.map((turn) => <div key={turn.id} className="copilot-turn"><ChatQuestion role={role}>{turn.question}</ChatQuestion>{turn.status === "processing" ? <article className="copilot-processing-message"><div className="copilot-processing-head"><span><IconSparkles aria-hidden="true" /> Copilot is working</span><IconLoader className="copilot-processing-loader" aria-hidden="true" /></div><p>Reviewing your question and preparing a clear answer.</p></article> : null}{turn.status === "completed" ? <SummaryCard question={turn.question} textSummary={turn.report?.textSummary} data={turn.report?.data} heroMetric={turn.report?.heroMetric} kpiCards={turn.report?.kpiCards} status="Completed" queryId={turn.queryId} executionTimeMs={turn.executionTimeMs} askedAt={turn.askedAt} /> : null}{turn.status === "failed" ? <ConversationFeedback title="I couldn’t complete that request.">{turn.errorMessage}</ConversationFeedback> : null}</div>)}<div ref={threadEndRef} /></section>;
}

export function CopilotComposer({ question, setQuestion, onSubmit, sending }) {
  return <form className="copilot-composer" onSubmit={(event) => { event.preventDefault(); onSubmit(question); }}><input aria-label="Ask a question" placeholder="Ask a question about your business..." value={question} onChange={(event) => setQuestion(event.target.value)} disabled={sending} /><button type="submit" aria-label="Send question" disabled={sending}><IconSend aria-hidden="true" /></button></form>;
}
