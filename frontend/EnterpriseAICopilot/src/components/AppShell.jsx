import Sidebar from './Sidebar'
import AppTopBar from './AppTopBar'

export default function AppShell({ active, title, mainClassName = '', children }) {
  return (
    <main className="copilot-shell">
      <Sidebar active={active} />
      <section className={['copilot-main', mainClassName].filter(Boolean).join(' ')}>
        {title ? <AppTopBar title={title} /> : null}
        {children}
      </section>
    </main>
  )
}
