import { IconUser } from './icons'

export default function ChatQuestion({ children, isAdmin = false, role }) {
  const displayRole = role || (isAdmin ? 'admin' : 'normal')
  return (
    <article className="chat-question-card">
      <div className="chat-question-meta">
        <span className="chat-question-avatar"><IconUser aria-hidden="true" /></span>
        <span>Your question</span>
        <span className="chat-question-role">{displayRole === 'admin' ? 'Admin' : 'User'}</span>
      </div>
      <p>{children}</p>
    </article>
  )
}
