import { IconAlertCircle } from './icons'
import '../styles/summary-card.css'

export default function ConversationFeedback({ title, children }) {
  return (
    <article className="conversation-feedback">
      <span className="conversation-feedback-icon"><IconAlertCircle aria-hidden="true" /></span>
      <div>
        <p>Copilot</p>
        <h2>{title}</h2>
        <span>{children}</span>
      </div>
    </article>
  )
}
