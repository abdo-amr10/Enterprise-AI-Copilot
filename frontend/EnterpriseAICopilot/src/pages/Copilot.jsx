import { useState } from 'react'
import '../styles/copilot.css'
import AppSidebar from '../components/AppSidebar'
import AppTopBar from '../components/AppTopBar'

function Copilot() {
  const [state, setState] = useState('empty')
  const [question, setQuestion] = useState('')
  const ask = (value = question) => {
    if (!value.trim()) return
    setQuestion(value)
    setState('processing')
    window.setTimeout(() => setState('success'), 850)
  }

  const content = () => {
    if (state === 'processing') return <div className="copilot-result-state copilot-chat-state"><div className="copilot-user-message">{question}</div><div className="copilot-ai-message"><b>AI Copilot</b><div className="copilot-thinking"><span /><span /><span /></div><p>Checking approved data and preparing a read-only answer…</p></div></div>
    if (state === 'success') return <div className="copilot-result-state copilot-success"><p className="copilot-kicker">ANSWER READY</p><h2>Total revenue this month</h2><p className="copilot-result-value">$145,000</p><p className="copilot-intro">Active customers generated <strong>$145,000</strong> in revenue this month. This result is based on the approved Sales and Customers semantic data.</p><div className="copilot-result-meta"><span>Summary</span><span>Read-only result</span><button type="button" onClick={() => setState('empty')}>New question</button></div></div>
    if (state === 'safety') return <div className="copilot-result-state copilot-error"><div className="copilot-error-icon">!</div><p className="copilot-kicker">REQUEST NOT PROCESSED</p><h2>I can only help with safe data questions.</h2><p className="copilot-intro">Try rephrasing your request as a question about approved, read-only enterprise information.</p><button type="button" onClick={() => setState('empty')}>Try another question</button></div>
    if (state === 'system') return <div className="copilot-result-state copilot-error"><div className="copilot-error-icon">×</div><p className="copilot-kicker">SERVICE UNAVAILABLE</p><h2>We couldn’t complete that request.</h2><p className="copilot-intro">The Copilot service is temporarily unavailable. Please try again in a moment.</p><button type="button" onClick={() => setState('empty')}>Back to Copilot</button></div>
    return <div className="copilot-result-state"><p className="copilot-kicker">YOUR INTELLIGENCE, ON DEMAND</p><h2>What would you like to know?</h2><p className="copilot-intro">Ask questions in plain language. Your answers are generated from approved enterprise data and always respect your access permissions.</p><div className="copilot-prompts"><button type="button" onClick={() => ask('Show monthly revenue by branch')}>Show monthly revenue by branch</button><button type="button" onClick={() => ask('Which customers are currently inactive?')}>Which customers are currently inactive?</button><button type="button" onClick={() => ask('Compare this quarter to the previous one')}>Compare this quarter to the previous one</button></div></div>
  }

  return (
    <main className="copilot-shell">
      <AppSidebar active="copilot" />
      <section className="copilot-main">
        <AppTopBar title="Ask your data" />
        <div className="copilot-workspace">{content()}</div>
        <form className="copilot-composer" onSubmit={(event) => { event.preventDefault(); ask() }}><input aria-label="Ask a question" placeholder="Ask a question about your data..." value={question} onChange={(event) => setQuestion(event.target.value)} disabled={state === 'processing'} /><button type="submit" aria-label="Send question" disabled={state === 'processing'}>↑</button></form>
        <p className="copilot-security-note">Answers are read-only and generated from approved semantic data.</p>
        <div className="copilot-state-preview" aria-label="UI state preview"><button type="button" onClick={() => setState('empty')}>Empty</button><button type="button" onClick={() => setState('processing')}>Processing</button><button type="button" onClick={() => setState('success')}>Success</button><button type="button" onClick={() => setState('safety')}>Safety</button><button type="button" onClick={() => setState('system')}>System</button></div>
      </section>
    </main>
  )
}

export default Copilot
