import { useState } from 'react'
import { Link } from 'react-router-dom'
import AdminSidebar from '../components/AdminSidebar'
import AdminTopBar from '../components/AdminTopBar'
import { IconBookOpen, IconCheck, IconDatabase, IconFileText, IconLayers, IconTable, IconX } from '../components/icons'
import '../styles/admin.css'
import '../styles/admin-pages.css'

const sources = [
  [IconLayers, 'Schema Definition', 'JSON or YAML', 'erp_semantic_schema.json', '14 KB'],
  [IconBookOpen, 'Documentation', 'Markdown or PDF', 'analytics_docs.md', '42 KB'],
  [IconTable, 'Business Glossary', 'CSV or Excel', 'enterprise_terms_mapping.csv', '8 KB'],
  [IconDatabase, 'Sample Data', 'CSV, Parquet, or JSONL', 'sample_cohort_1000.parquet', '8.12 MB'],
]

function UploadSources({ onCancel }) {
  const [loading, setLoading] = useState(false)
  return <section className="source-upload">
    <div className="source-details"><h3>Data Source Details</h3><div className="source-divider" /><div className="source-fields"><label>Source Name <b>*</b><input defaultValue="Customer Journey Q3 2024 Analytics" /></label><label>Description <small>(Optional)</small><input defaultValue="Aggregated telemetry and support ticket metadata for Q3 cohort" /></label></div></div>
    <div className="source-files-heading"><h3>Required Files</h3><span>4 / 4 Uploaded</span></div>
    <div className="source-grid">{sources.map(([Icon, title, type, file, size]) => <article key={title} className="source-file-card"><div className="source-file-top"><div><span className="source-type-icon"><Icon aria-hidden="true" /></span><strong>{title}</strong><small>{type}</small></div><button type="button" aria-label={`Remove ${title}`}><IconX aria-hidden="true" /></button></div><div className="source-file-ready"><IconFileText aria-hidden="true" /><div><b>{file}</b><small>{size} · Ready</small></div><span><IconCheck aria-hidden="true" /></span></div></article>)}</div>
    <div className="source-footer"><button type="button" onClick={onCancel}>Cancel</button><button className="primary" type="button" onClick={() => { setLoading(true); window.setTimeout(() => setLoading(false), 750) }}>{loading ? 'Loading sources…' : <><IconDatabase aria-hidden="true" /> Load Data Sources</>}</button></div>
  </section>
}

export default function AdminSemanticLayer() {
  const [tab, setTab] = useState('overview')
  const [generation, setGeneration] = useState('full')
  return <main className="admin-shell"><AdminSidebar active="semantic" /><section className="admin-main"><AdminTopBar title="Semantic Layer" description="Maintain the approved business context that powers Copilot answers." /><div className="admin-tabs"><button className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>Overview</button><button className={tab === 'upload' ? 'active' : ''} onClick={() => setTab('upload')}>Data Sources</button><button className={tab === 'generate' ? 'active' : ''} onClick={() => setTab('generate')}>Generate Draft</button><Link to="/admin/review">Review drafts</Link></div>
    {tab === 'overview' && <div className="admin-content-grid"><article className="admin-card"><div className="admin-card-title"><div><small>CURRENT LAYER</small><h3>ERP Semantic Layer</h3></div><span className="admin-badge">Approved · v1.2</span></div><p>Last built Aug 15, 2026 at 3:00 PM · Incremental update</p><div className="admin-key-values"><span><b>24</b> Entities</span><span><b>18</b> Measures</span><span><b>31</b> Relationships</span><span><b>12</b> Business rules</span></div><button onClick={() => setTab('upload')}>Update sources</button></article><article className="admin-card"><small>WORKFLOW</small><h3>Generate a new draft</h3><p>Upload approved data sources, then generate a full or incremental semantic draft for review.</p><button onClick={() => setTab('generate')}>Generate draft</button></article></div>}
    {tab === 'upload' && <UploadSources onCancel={() => setTab('overview')} />}
    {tab === 'generate' && <article className="admin-card admin-form"><small>GENERATION</small><h3>Generate semantic draft</h3><p>Create a revision from your uploaded sources. Nothing is published until an Admin approves it.</p><div className="admin-choice"><button className={generation === 'full' ? 'selected' : ''} onClick={() => setGeneration('full')}><b>Full rebuild</b><span>Regenerate all semantic objects</span></button><button className={generation === 'incremental' ? 'selected' : ''} onClick={() => setGeneration('incremental')}><b>Incremental</b><span>Update selected changed objects</span></button></div><div className="admin-actions"><button onClick={() => setTab('overview')}>Back</button><button className="primary">Generate draft</button></div></article>}
  </section></main>
}
