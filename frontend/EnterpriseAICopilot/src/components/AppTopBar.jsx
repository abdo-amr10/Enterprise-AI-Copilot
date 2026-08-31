export default function AppTopBar({ title, label = "ENTERPRISE AI COPILOT" }) {
  return (
    <header className="copilot-header">
      <div>
        <p>{label}</p>
        <h1>{title}</h1>
      </div>
      <div className="copilot-status">
        <i /> Secure session
      </div>
    </header>
  );
}
