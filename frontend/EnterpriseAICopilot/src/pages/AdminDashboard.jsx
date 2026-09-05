import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Logo from '../assets/Logo.png'
import AdminSidebar from '../components/AdminSidebar'
import AdminTopBar from '../components/AdminTopBar'
import { getSemanticLayers } from '../services/semanticLayerService'
import { fetchAuditLogs } from '../services/auditService'
import '../styles/admin.css'

function formatTimestamp(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function AdminDashboard() {
  const [state, setState] = useState('loading')
  const [layer, setLayer] = useState(null)
  const [activity, setActivity] = useState([])

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([getSemanticLayers(), fetchAuditLogs()]).then(([layersResult, auditResult]) => {
      if (cancelled) return
      if (layersResult.status === 'fulfilled') setLayer(layersResult.value.find((item) => item.isActive) || layersResult.value[0] || null)
      if (auditResult.status === 'fulfilled') {
        const logs = auditResult.value?.items || auditResult.value?.data || (Array.isArray(auditResult.value) ? auditResult.value : [])
        setActivity(logs.slice(0, 3))
      }
      setState(layersResult.status === 'rejected' && auditResult.status === 'rejected' ? 'error' : 'ready')
    })
    return () => { cancelled = true }
  }, [])

  return (
    <main className="admin-shell">
      <AdminSidebar active="dashboard" />
      <section className="admin-main admin-dashboard-main">
        <AdminTopBar title="System overview" description="Review semantic-layer status, manage users, and monitor activity from one secure workspace." />
        <section className="admin-hero"><div><p>ENTERPRISE INTELLIGENCE</p><h2>Manage the data foundation behind your Copilot.</h2><span>Live information from your connected workspace.</span></div><img src={Logo} alt="" /></section>
        {state === 'error' ? <p className="admin-error" role="alert">We couldn’t load the dashboard right now. Please try again later.</p> : null}
        <section className="admin-stats">
          <article><small>SEMANTIC LAYER</small><strong>{layer?.hasApprovedRevision ? 'Approved' : layer ? 'Pending' : '—'}</strong><span>{layer?.name || 'No layer available'}</span></article>
          <article><small>ACTIVE USERS</small><strong>—</strong><span>Live metric not available</span></article>
          <article><small>QUESTIONS TODAY</small><strong>—</strong><span>Live metric not available</span></article>
        </section>
        <section className="admin-grid">
          <article className="admin-card"><div className="admin-card-title"><div><small>SEMANTIC LAYER</small><h3>{layer?.name || 'No semantic layer available'}</h3></div><span className="admin-badge">{layer?.hasApprovedRevision ? 'Approved' : layer ? 'Pending' : 'Unavailable'}</span></div><p>{layer ? `Database: ${layer.databaseName || 'Not specified'}` : 'Create a semantic layer to connect your business context.'}</p><Link to="/admin/semantic-layers">View semantic layers</Link></article>
          <article className="admin-card"><div className="admin-card-title"><div><small>RECENT ACTIVITY</small><h3>Audit snapshot</h3></div></div>{activity.length ? <ul>{activity.map((item, index) => <li key={item.id || item.auditLogId || index}><b>{item.action || item.eventType || 'Activity recorded'}</b><span>{formatTimestamp(item.timestamp || item.createdAt)}</span></li>)}</ul> : <p>No recent activity available.</p>}<Link to="/admin/audit-logs">Open audit logs</Link></article>
        </section>
      </section>
    </main>
  )
}
