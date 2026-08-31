import Logo from '../assets/Logo.png'
import '../styles/admin.css'
import AdminSidebar from '../components/AdminSidebar'

function AdminDashboard() {
  return <main className="admin-shell">
    <AdminSidebar active="dashboard" />
    <section className="admin-main"><header className="admin-header"><div><p>ADMIN CONSOLE</p><h1>System overview</h1></div><span className="admin-live"><i /> All systems operational</span></header>
      <section className="admin-hero"><div><p>ENTERPRISE INTELLIGENCE</p><h2>Manage the data foundation behind your Copilot.</h2><span>Review semantic-layer status, manage users, and monitor activity from one secure workspace.</span></div><img src={Logo} alt="" /></section>
      <section className="admin-stats"><article><small>SEMANTIC LAYER</small><strong>Approved</strong><span>Version v1.2</span></article><article><small>ACTIVE USERS</small><strong>248</strong><span>Across 12 branches</span></article><article><small>QUESTIONS TODAY</small><strong>186</strong><span>98.9% completed</span></article></section>
      <section className="admin-grid"><article className="admin-card"><div className="admin-card-title"><div><small>SEMANTIC LAYER</small><h3>ERP Semantic Layer</h3></div><span className="admin-badge">Approved</span></div><p>Last regenerated Aug 15, 2026 · Full rebuild</p><button>View semantic layer</button></article><article className="admin-card"><div className="admin-card-title"><div><small>RECENT ACTIVITY</small><h3>Audit snapshot</h3></div></div><ul><li><b>Revision rev-102 approved</b><span>24 min ago</span></li><li><b>New user registered</b><span>1 hr ago</span></li><li><b>Query execution completed</b><span>2 hrs ago</span></li></ul><button>Open audit logs</button></article></section>
    </section>
  </main>
}
export default AdminDashboard
