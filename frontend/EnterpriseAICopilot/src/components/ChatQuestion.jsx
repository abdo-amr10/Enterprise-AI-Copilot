import { IconUser } from './icons'

export default function ChatQuestion({ children, isAdmin = false }) {
  return (
    <article className="chat-question-card">
      <div className="chat-question-meta">
        <span className="chat-question-avatar"><IconUser aria-hidden="true" /></span>
        <span>Your question</span>
        {isAdmin ? <span className="chat-question-role">Admin</span> : null}
      </div>
      <p>{children}</p>
    </article>
  )
}
