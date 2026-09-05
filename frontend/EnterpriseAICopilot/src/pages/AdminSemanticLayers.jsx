import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import AdminSidebar from '../components/AdminSidebar'
import AdminTopBar from '../components/AdminTopBar'
import ConfirmDialog from '../components/ConfirmDialog'
import { IconCheck, IconDatabase, IconExternalLink, IconLayers, IconLoader, IconSearch, IconTrash } from '../components/icons'
import { activateSemanticLayer, deleteSemanticLayer, getSemanticLayers } from '../services/semanticLayerService'
import '../styles/admin.css'
import '../styles/admin-pages.css'
import '../styles/semantic-layers.css'

function LayerStatus({ layer }) {
  return (
    <div className="semantic-layer-statuses">
      <span className={`semantic-layer-badge ${layer.isActive ? 'is-active' : 'is-inactive'}`}>
        <i aria-hidden="true" />{layer.isActive ? 'Active' : 'Inactive'}
      </span>
      <span className={`semantic-layer-badge ${layer.hasApprovedRevision ? 'is-approved' : 'is-pending'}`}>
        {layer.hasApprovedRevision ? <IconCheck aria-hidden="true" /> : null}
        {layer.hasApprovedRevision ? 'Approved revision' : 'No approved revision'}
      </span>
    </div>
  )
}

function LoadingState() {
  return <section className="semantic-layers-state" aria-live="polite"><IconLoader className="copilot-processing-loader" aria-hidden="true" /><h2>Loading semantic layers</h2><p>Preparing your data contexts.</p></section>
}

function EmptyState({ filtered, onClear }) {
  return <section className="semantic-layers-state"><IconLayers aria-hidden="true" /><h2>{filtered ? 'No matching layers' : 'No semantic layers yet'}</h2><p>{filtered ? 'Try a different search or filter.' : 'Create a data source to start building the business context for Copilot.'}</p>{filtered ? <button type="button" onClick={onClear}>Clear filters</button> : <Link className="primary" to="/admin/semantic-layer/upload">Add data source</Link>}</section>
}

export default function AdminSemanticLayers() {
  const [layers, setLayers] = useState([])
  const [state, setState] = useState('loading')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [notice, setNotice] = useState('')
  const [pendingAction, setPendingAction] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const loadLayers = useCallback(async ({ clearNotice = true } = {}) => {
    setState('loading')
    if (clearNotice) setNotice('')
    try {
      setLayers(await getSemanticLayers())
      setState('ready')
    } catch {
      setState('error')
    }
  }, [])

  useEffect(() => { Promise.resolve().then(loadLayers) }, [loadLayers])

  const visibleLayers = useMemo(() => layers.filter((layer) => {
    const matchesQuery = `${layer.name} ${layer.description} ${layer.databaseName}`.toLowerCase().includes(query.trim().toLowerCase())
    const matchesFilter = filter === 'all' || (filter === 'active' ? layer.isActive : !layer.isActive)
    return matchesQuery && matchesFilter
  }), [filter, layers, query])

  const clearFilters = () => { setQuery(''); setFilter('all') }

  async function confirmAction() {
    if (!pendingAction) return
    setIsSubmitting(true)
    try {
      if (pendingAction.type === 'activate') {
        await activateSemanticLayer(pendingAction.layer.id)
        setNotice(`“${pendingAction.layer.name}” is now the active semantic layer.`)
      } else {
        await deleteSemanticLayer(pendingAction.layer.id)
        setNotice(`“${pendingAction.layer.name}” was deleted.`)
      }
      setPendingAction(null)
      await loadLayers({ clearNotice: false })
    } catch (error) {
      setNotice(error.message || 'We could not complete that request. Please try again.')
      setPendingAction(null)
    } finally {
      setIsSubmitting(false)
    }
  }

  const hasFilters = Boolean(query.trim()) || filter !== 'all'
  return (
    <main className="admin-shell">
      <AdminSidebar active="semantic" />
      <section className="admin-main semantic-layers-main">
        <AdminTopBar title="Semantic Layers" description="Manage the approved business contexts that help Copilot answer accurately." />
        <div className="semantic-layers-toolbar">
          <label className="semantic-layer-search">
            <IconSearch aria-hidden="true" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search layers" aria-label="Search semantic layers" />
          </label>
          <label className="semantic-layer-filter">Status<select value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Filter semantic layers by status"><option value="all">All layers</option><option value="active">Active</option><option value="inactive">Inactive</option></select></label>
          <Link className="primary semantic-layer-add" to="/admin/semantic-layer/upload"><IconDatabase aria-hidden="true" /> Add data source</Link>
        </div>
        {notice ? <p className="semantic-layer-notice" role="status">{notice}</p> : null}
        {state === 'loading' ? <LoadingState /> : null}
        {state === 'error' ? <section className="semantic-layers-state"><h2>We couldn’t load semantic layers</h2><p>Please check your connection and try again.</p><button type="button" className="primary" onClick={loadLayers}>Try again</button></section> : null}
        {state === 'ready' && visibleLayers.length === 0 ? <EmptyState filtered={hasFilters} onClear={clearFilters} /> : null}
        {state === 'ready' && visibleLayers.length > 0 ? <section className="semantic-layer-list" aria-label="Semantic layers">{visibleLayers.map((layer) => <article className={`semantic-layer-row ${layer.isActive ? 'is-active' : ''}`} key={layer.id}><div className="semantic-layer-row-icon"><IconLayers aria-hidden="true" /></div><div className="semantic-layer-copy"><div className="semantic-layer-title"><h2>{layer.name}</h2>{layer.isActive ? <span>Current active layer</span> : null}</div><p>{layer.description || 'No description provided.'}</p><div className="semantic-layer-meta"><span><IconDatabase aria-hidden="true" />{layer.databaseName || 'Database not specified'}</span><LayerStatus layer={layer} /></div></div><div className="semantic-layer-actions"><Link to={`/admin/semantic-layers/${layer.id}`}>Open details <IconExternalLink aria-hidden="true" /></Link>{!layer.isActive && layer.hasApprovedRevision ? <button className="semantic-layer-activate" type="button" onClick={() => setPendingAction({ type: 'activate', layer })}>Activate</button> : null}{!layer.isActive && !layer.hasApprovedRevision ? <span className="semantic-layer-action-note">Approval needed</span> : null}<button className="semantic-layer-delete" type="button" aria-label={`Delete ${layer.name}`} onClick={() => setPendingAction({ type: 'delete', layer })}><IconTrash aria-hidden="true" /></button></div></article>)}</section> : null}
      </section>
      <ConfirmDialog open={Boolean(pendingAction)} title={pendingAction?.type === 'delete' ? 'Delete semantic layer?' : 'Activate this semantic layer?'} message={pendingAction?.type === 'delete' ? 'This removes the semantic layer and its related data. This action cannot be undone.' : 'This makes the selected layer the business context used by Copilot.'} confirmLabel={pendingAction?.type === 'delete' ? 'Delete layer' : 'Activate layer'} variant={pendingAction?.type === 'delete' ? 'destructive' : 'primary'} isBusy={isSubmitting} onConfirm={confirmAction} onCancel={() => !isSubmitting && setPendingAction(null)} />
    </main>
  )
}
