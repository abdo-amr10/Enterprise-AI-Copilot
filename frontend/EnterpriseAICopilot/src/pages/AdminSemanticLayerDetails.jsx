import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import AdminSidebar from '../components/AdminSidebar'
import AdminTopBar from '../components/AdminTopBar'
import ConfirmDialog from '../components/ConfirmDialog'
import { IconArrowLeft, IconCheck, IconDatabase, IconDownload, IconFileText, IconLayers, IconLoader, IconTable } from '../components/icons'
import { fetchUsers } from '../services/adminUsersService'
import { deleteSemanticSourceFile, generateSemanticDraft, getSemanticLayerById, getSemanticLayerStatus, getSemanticLayerTablePermissions, getSemanticLayerTables, getSemanticSourceFile, getSemanticSourceFileContent, normalizeSemanticSources, setSemanticLayerTableAccess, setUserTableAccess, upsertSemanticSourceFile } from '../services/semanticLayerService'
import '../styles/admin.css'
import '../styles/admin-pages.css'
import '../styles/semantic-layer-details.css'

const TABS = [
  { key: 'overview', label: 'Overview', title: 'Layer overview', description: 'See the current business context and its approved revision.' },
  { key: 'sources', label: 'Data sources', title: 'Data sources', description: 'Manage the files that define this business context.' },
  { key: 'generate', label: 'Generate draft', title: 'Generate a draft', description: 'Prepare an updated business context for review.' },
  { key: 'revisions', label: 'Revisions', title: 'Revisions', description: 'Review the versions created for this semantic layer.' },
  { key: 'tables', label: 'Tables', title: 'Tables', description: 'Manage the business tables included in this layer.' },
  { key: 'permissions', label: 'Permissions', title: 'Table permissions', description: 'Control which users can access each business table.' },
]

const SOURCE_TYPES = [
  { key: 'schema', apiType: 'schema', sourceKey: 'schemaFileId', label: 'Schema definition', description: 'SQL or JSON database schema', accept: '.sql,.json', required: true },
  { key: 'documentation', apiType: 'documentation', sourceKey: 'documentationFileId', label: 'Documentation', description: 'Supporting business documentation', accept: '.pdf,.md,.txt,.doc,.docx' },
  { key: 'glossary', apiType: 'glossary', sourceKey: 'glossaryFileId', label: 'Business glossary', description: 'Shared business terminology', accept: '.csv,.xlsx,.xls,.pdf,.md,.txt' },
  { key: 'sampleData', apiType: 'sampledata', sourceKey: 'sampleDataFileId', label: 'Sample data', description: 'Representative sample records', accept: '.csv,.json,.parquet' },
]

function formatTimestamp(value) {
  const date = new Date(value)
  return value && !Number.isNaN(date.getTime())
    ? date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
    : 'Not available'
}

function uploadedSourceFiles(sources) {
  if (!sources) return {}
  return Object.fromEntries(SOURCE_TYPES
    .map(({ key, apiType, sourceKey }) => {
      const pascalKey = sourceKey[0].toUpperCase() + sourceKey.slice(1)
      const fileId = sources[sourceKey] ?? sources[pascalKey]
      return [key, fileId ? { fileId, fileType: apiType } : null]
    })
    .filter(([, source]) => source))
}

function SourceCard({ source, isLoading, isBusy, actionLabel, onDownload, onUpload, onDelete }) {
  const hasFile = Boolean(source.fileId)
  return <article className={`semantic-source-card ${hasFile ? 'has-file' : ''}`}>
    <div className="semantic-source-card-heading"><div className="semantic-source-icon"><IconFileText aria-hidden="true" /></div><div><h3>{source.label}{source.required ? <em> *</em> : null}</h3><p>{source.description}</p></div>{hasFile ? <span className="semantic-source-ready"><IconCheck aria-hidden="true" />Ready</span> : <span className="semantic-source-empty">No file</span>}</div>
    {isLoading ? <div className="semantic-source-loading"><IconLoader className="copilot-processing-loader" aria-hidden="true" />Loading file details</div> : hasFile ? <div className="semantic-source-file"><IconFileText aria-hidden="true" /><div><strong>{source.fileName || 'Source file'}</strong><span>{source.fileType || source.label}</span></div></div> : <div className="semantic-source-file is-empty"><IconFileText aria-hidden="true" /><div><strong>No file selected</strong><span>Add or update this source when it is ready.</span></div></div>}
    <div className="semantic-source-actions">{hasFile ? <button type="button" disabled={isBusy} onClick={() => onDownload(source)}>{actionLabel === 'Preparing…' ? actionLabel : <><IconDownload aria-hidden="true" />Download</>}</button> : null}<label className={isBusy ? 'is-disabled' : ''}><input type="file" accept={source.accept} disabled={isBusy} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) onUpload(source, file) }} />{isBusy ? actionLabel : hasFile ? 'Replace' : 'Upload'}</label>{hasFile ? <button type="button" className="is-destructive" disabled={isBusy} onClick={() => onDelete(source)}>Remove</button> : null}</div>
  </article>
}

function OverviewTab({ layer, status }) {
  const sourceCount = Object.values(status?.sources || {}).filter(Boolean).length
  return <section className="semantic-details-workspace"><span className="semantic-details-kicker">Layer overview</span><h2>Business context at a glance</h2><p>This layer provides the approved context that helps Copilot understand your organization’s data.</p><div className="semantic-overview-grid"><div><small>LAYER STATUS</small><strong>{layer.isActive ? 'Active' : 'Inactive'}</strong></div><div><small>LATEST REVISION</small><strong>{status?.version || 'No revision yet'}</strong></div><div><small>REVISION STATUS</small><strong>{status?.status || 'Not available'}</strong></div><div><small>DATA SOURCES</small><strong>{status ? `${sourceCount} connected` : 'Not available'}</strong></div><div><small>LAST UPDATED</small><strong>{formatTimestamp(status?.buildTimestamp)}</strong></div><div><small>LAST GENERATION</small><strong>{status?.lastRegenerationType || 'Not available'}</strong></div></div>{!layer.isActive ? <p className="semantic-details-note">Revision details become available here when this layer is active.</p> : null}</section>
}

function SourcesTab({ layer, status, sourceFiles, sourceState, actionKey, onDownload, onUpload, onDelete }) {
  // Status is the canonical source of persisted file IDs when a revision exists.
  // Keep the layer/upload values as secondary data so a metadata request cannot
  // make an already persisted source disappear from the UI.
  const sourceIds = { ...(layer?.sources || {}), ...(status?.sources || {}) }
  const sources = SOURCE_TYPES.map((type) => ({ ...type, fileId: sourceIds[type.sourceKey] || sourceFiles[type.key]?.fileId || '', ...sourceFiles[type.key] }))
  return <section className="semantic-details-workspace semantic-sources-workspace"><div className="semantic-sources-intro"><div><span className="semantic-details-kicker">Data sources</span><h2>Files that shape this layer</h2></div><span>{sources.filter((source) => source.fileId).length} / {sources.length} available</span></div><div className="semantic-sources-grid">{sources.map((source) => <SourceCard key={source.key} source={source} isLoading={sourceState === 'loading' && Boolean(source.fileId)} isBusy={actionKey === source.key || actionKey === `download:${source.key}`} actionLabel={actionKey === `download:${source.key}` ? 'Preparing…' : 'Saving…'} onDownload={onDownload} onUpload={onUpload} onDelete={onDelete} />)}</div></section>
}

function GenerateDraftTab({ layer, status, sourceFiles, onGenerated }) {
  const [generationType, setGenerationType] = useState('FullRebuild')
  const [isConfirming, setIsConfirming] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState('')

  const sourceFileIds = useMemo(() => ({
    schema: status?.sources?.schemaFileId || sourceFiles.schema?.fileId || null,
    documentation: status?.sources?.documentationFileId || sourceFiles.documentation?.fileId || null,
    glossary: status?.sources?.glossaryFileId || sourceFiles.glossary?.fileId || null,
    sampleData: status?.sources?.sampleDataFileId || sourceFiles.sampleData?.fileId || null,
  }), [sourceFiles, status])
  const hasSchema = Boolean(sourceFileIds.schema)
  const canUseIncremental = Boolean(status?.revisionId)
  const canGenerate = hasSchema && (generationType !== 'Incremental' || canUseIncremental)

  function requestGeneration() {
    setError('')
    if (!hasSchema) {
      setError('Add a schema definition before generating a draft.')
      return
    }
    if (generationType === 'Incremental' && !canUseIncremental) {
      setError('An existing revision is required for an incremental update.')
      return
    }
    setIsConfirming(true)
  }

  async function generate() {
    setIsGenerating(true)
    setError('')
    try {
      const response = await generateSemanticDraft({
        semanticLayerId: layer.id,
        triggerType: generationType,
        sourceFileIds,
        baseRevisionId: generationType === 'Incremental' ? status?.revisionId : null,
      })
      if (!response?.revisionId) throw new Error('The draft was created, but no revision was returned. Please try again.')
      onGenerated(response)
    } catch (nextError) {
      setError(nextError.message || 'We couldn’t generate a draft. Please try again.')
    } finally {
      setIsGenerating(false)
      setIsConfirming(false)
    }
  }

  return <section className="semantic-details-workspace semantic-generate-workspace">
    <span className="semantic-details-kicker">Generate draft</span>
    <h2>Create a new semantic draft</h2>
    <p>Use the saved business sources to prepare a revision for review. It will not affect Copilot until it is approved and activated.</p>
    <div className="semantic-generate-options" role="radiogroup" aria-label="Draft generation type">
      <button type="button" role="radio" aria-checked={generationType === 'FullRebuild'} className={generationType === 'FullRebuild' ? 'selected' : ''} onClick={() => setGenerationType('FullRebuild')} disabled={isGenerating}><strong>Full rebuild</strong><span>Recreate the complete business context from the current files.</span></button>
      <button type="button" role="radio" aria-checked={generationType === 'Incremental'} className={generationType === 'Incremental' ? 'selected' : ''} onClick={() => setGenerationType('Incremental')} disabled={!canUseIncremental || isGenerating}><strong>Incremental update</strong><span>{canUseIncremental ? 'Build from the current approved revision.' : 'Available when this layer has an existing revision.'}</span></button>
    </div>
    <div className="semantic-generation-summary"><div><small>SCHEMA DEFINITION</small><strong>{hasSchema ? 'Ready to use' : 'Required before generating'}</strong></div><div><small>CURRENT REVISION</small><strong>{status?.version || 'No revision yet'}</strong></div><div><small>GENERATION TYPE</small><strong>{generationType === 'FullRebuild' ? 'Full rebuild' : 'Incremental update'}</strong></div></div>
    {error ? <p className="semantic-generation-error" role="alert">{error}</p> : null}
    {isGenerating ? <div className="semantic-generating" aria-live="polite"><IconLoader className="copilot-processing-loader" aria-hidden="true" /><div><strong>Generating your semantic draft</strong><span>This may take a moment. You can stay on this page while we prepare it.</span></div></div> : null}
    <div className="semantic-generate-actions"><Link to={`/admin/semantic-layers/${layer.id}/sources`}>Review sources</Link><button type="button" className="primary" disabled={isGenerating || !canGenerate} onClick={requestGeneration}>Generate draft</button></div>
    <ConfirmDialog open={isConfirming} title="Generate semantic draft?" message={generationType === 'FullRebuild' ? 'This creates a new complete draft from the current data sources. It will be sent to review before it can be used by Copilot.' : 'This creates a focused update from the current revision and saved data sources. It will be sent to review before it can be used by Copilot.'} confirmLabel="Generate draft" isBusy={isGenerating} onConfirm={generate} onCancel={() => !isGenerating && setIsConfirming(false)} />
  </section>
}

function RevisionsTab({ layer, status }) {
  const revisionId = status?.revisionId
  return <section className="semantic-details-workspace semantic-revisions-workspace"><div className="semantic-management-heading"><div><span className="semantic-details-kicker">Revisions</span><h2>Review the business context</h2><p>Each generated draft is reviewed before it can be made available to Copilot.</p></div></div>{revisionId ? <article className="semantic-revision-row"><div><strong>{status?.version || 'Current revision'}</strong><span>{status?.lastRegenerationType || 'Generated revision'} · {formatTimestamp(status?.buildTimestamp)}</span></div><Link className="primary" to={`/admin/semantic-layers/${layer.id}/revisions/${revisionId}/review`}>Open revision</Link></article> : <div className="semantic-management-state semantic-revisions-empty"><IconLayers aria-hidden="true" /><div><strong>No revision is ready to review</strong><span>Generate a draft to begin the review and approval process.</span></div><Link to={`/admin/semantic-layers/${layer.id}/generate`}>Generate draft</Link></div>}<p className="semantic-details-note">After a revision is approved, return to Semantic Layers and activate the layer when you are ready to use it in Copilot.</p></section>
}

function useLayerTables(layer) {
  const [tableState, setTableState] = useState('loading')
  const [tables, setTables] = useState([])
  const loadTables = useCallback(async () => {
    if (!layer?.id) { setTables([]); setTableState('empty'); return }
    setTableState('loading')
    try {
      const nextTables = await getSemanticLayerTables(layer.id)
      setTables(nextTables)
      setTableState(nextTables.length ? 'ready' : 'empty')
    } catch {
      setTableState('error')
    }
  }, [layer])
  useEffect(() => { Promise.resolve().then(loadTables) }, [loadTables])
  return { tableState, tables, setTables, loadTables }
}

function TablesTab({ layer }) {
  const { tableState, tables, setTables, loadTables } = useLayerTables(layer)
  const [query, setQuery] = useState('')
  const [savingTable, setSavingTable] = useState('')
  const [notice, setNotice] = useState(null)
  const visibleTables = tables.filter((table) => table.name.toLowerCase().includes(query.trim().toLowerCase()))
  async function toggleTable(table) {
    const nextAllowed = !table.isAllowed
    setSavingTable(table.name)
    setNotice(null)
    try {
      await setSemanticLayerTableAccess({ layerId: layer.id, tableName: table.name, isAllowed: nextAllowed })
      setTables((current) => current.map((item) => item.name === table.name ? { ...item, isAllowed: nextAllowed } : item))
      setNotice({ type: 'success', text: `${table.name} is now ${nextAllowed ? 'available' : 'unavailable'} to Copilot.` })
    } catch (error) {
      setNotice({ type: 'error', text: error.message || `We couldn’t update ${table.name}.` })
    } finally { setSavingTable('') }
  }
  return <section className="semantic-details-workspace semantic-tables-workspace"><div className="semantic-management-heading"><div><span className="semantic-details-kicker">Tables</span><h2>Business tables in this layer</h2><p>Choose which tables Copilot can use when preparing answers.</p></div><span>{tables.length} tables</span></div>{tableState === 'loading' ? <div className="semantic-management-state"><IconLoader className="copilot-processing-loader" aria-hidden="true" />Loading tables</div> : null}{tableState === 'error' ? <div className="semantic-management-state is-error"><span>We couldn’t load tables for this layer.</span><button type="button" onClick={loadTables}>Try again</button></div> : null}{tableState === 'empty' ? <div className="semantic-management-state"><span>No tables are available for this layer yet.</span></div> : null}{tableState === 'ready' ? <><div className="semantic-management-toolbar"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tables" aria-label="Search tables" /><span>{visibleTables.length} shown</span></div>{notice ? <p className={`semantic-details-notice ${notice.type === 'error' ? 'is-error' : ''}`} role="status">{notice.text}</p> : null}<div className="semantic-table-list">{visibleTables.map((table) => <article key={table.name}><div className="semantic-table-name"><IconTable aria-hidden="true" /><div><strong>{table.name}</strong><span>{table.description || (table.columnCount ? `${table.columnCount} columns` : 'Included in this layer')}</span></div></div><label className="semantic-table-toggle"><input type="checkbox" checked={table.isAllowed} disabled={savingTable === table.name} onChange={() => toggleTable(table)} /><span aria-hidden="true" /><b>{savingTable === table.name ? 'Saving…' : table.isAllowed ? 'Available' : 'Unavailable'}</b></label></article>)}</div></> : null}</section>
}

function PermissionsTab({ layer }) {
  const semanticLayerId = layer?.id
  const requestSequence = useRef(0)
  const [users, setUsers] = useState([])
  const [usersState, setUsersState] = useState('loading')
  const [userQuery, setUserQuery] = useState('')
  const [selectedUserId, setSelectedUserId] = useState('')
  const [tables, setTables] = useState([])
  const [tablesState, setTablesState] = useState('loading')
  const [permissionUsers, setPermissionUsers] = useState([])
  const [permissionsState, setPermissionsState] = useState('loading')
  const [draft, setDraft] = useState({})
  const [savedDraft, setSavedDraft] = useState({})
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState(null)

  const loadData = useCallback(async () => {
    if (!semanticLayerId) return
    const sequence = ++requestSequence.current
    setUsers([]); setSelectedUserId(''); setTables([]); setPermissionUsers([]); setDraft({}); setSavedDraft({}); setUsersState('loading'); setPermissionsState('loading'); setTablesState('loading'); setNotice(null)
    const [usersResult, permissionsResult, tablesResult] = await Promise.allSettled([fetchUsers(), getSemanticLayerTablePermissions(semanticLayerId), getSemanticLayerTables(semanticLayerId)])
    if (sequence !== requestSequence.current) return
    if (usersResult.status === 'fulfilled') {
      const payload = usersResult.value?.data ?? usersResult.value
      const nextUsers = (Array.isArray(payload) ? payload : payload?.items || payload?.users || []).map((user) => ({ userId: user.userId ?? user.UserId, email: user.email ?? user.Email, name: `${user.firstName ?? ''} ${user.lastName ?? ''}`.trim() || user.fullName || user.email || user.Email })).filter((user) => user.userId && user.email)
      setUsers(nextUsers); setUsersState(nextUsers.length ? 'ready' : 'empty'); if (nextUsers.length) setSelectedUserId(nextUsers[0].userId)
    } else setUsersState('error')
    if (permissionsResult.status === 'fulfilled') { setPermissionUsers(permissionsResult.value.users || []); setPermissionsState('ready') } else setPermissionsState('error')
    if (tablesResult.status === 'fulfilled') { setTables(tablesResult.value || []); setTablesState('ready') } else setTablesState('error')
  }, [semanticLayerId])

  useEffect(() => { Promise.resolve().then(loadData) }, [loadData])
  const selectedUser = users.find((user) => String(user.userId).toLowerCase() === String(selectedUserId).toLowerCase())
  const selectedPermissionUser = permissionUsers.find((user) => String(user.userId).toLowerCase() === String(selectedUserId).toLowerCase())
  const baseline = Object.keys(savedDraft).length ? savedDraft : (selectedPermissionUser?.tables || {})
  const tableRows = tables.map((table) => ({ ...table, isAllowed: draft[table.name] ?? selectedPermissionUser?.tables?.[table.name] ?? false }))
  const allowedCount = tableRows.filter((table) => table.isAllowed).length
  const hasUnsavedChanges = tableRows.some((table) => Boolean(table.isAllowed) !== Boolean(baseline[table.name]))
  const visibleUsers = users.filter((user) => `${user.name} ${user.email}`.toLowerCase().includes(userQuery.trim().toLowerCase()))

  function selectUser(userId) { setSelectedUserId(userId); const next = permissionUsers.find((user) => String(user.userId).toLowerCase() === String(userId).toLowerCase()); setDraft(next?.tables || {}); setSavedDraft(next?.tables || {}); setNotice(null) }
  function toggleTable(tableName) { setDraft((current) => ({ ...current, [tableName]: !(current[tableName] ?? selectedPermissionUser?.tables?.[tableName] ?? false) })) }
  async function saveChanges() {
    if (!selectedUser || saving || !hasUnsavedChanges) return
    setSaving(true); setNotice(null)
    try {
      const changes = tableRows.filter((table) => Boolean(table.isAllowed) !== Boolean(baseline[table.name]))
      await Promise.all(changes.map((table) => setUserTableAccess({ layerId: semanticLayerId, email: selectedUser.email, tableName: table.name, isAllowed: Boolean(table.isAllowed) })))
      const nextTables = Object.fromEntries(tableRows.map((table) => [table.name, Boolean(table.isAllowed)]))
      setSavedDraft(nextTables); setDraft(nextTables); setPermissionUsers((current) => current.map((user) => String(user.userId).toLowerCase() === String(selectedUserId).toLowerCase() ? { ...user, tables: nextTables } : user)); setNotice({ type: 'success', text: 'Table access changes were saved.' })
    } catch (error) { setNotice({ type: 'error', text: error.message || 'We couldn’t save these access changes.' }) } finally { setSaving(false) }
  }

  return <section className="semantic-details-workspace semantic-permissions-workspace"><div className="semantic-management-heading"><div><span className="semantic-details-kicker">Table permissions</span><h2>Manage access to business tables</h2></div></div>{usersState === 'loading' || permissionsState === 'loading' || tablesState === 'loading' ? <div className="semantic-permission-loading"><IconLoader className="copilot-processing-loader" aria-hidden="true" />Loading users and permissions</div> : null}{usersState === 'error' ? <div className="semantic-management-state is-error"><span>We couldn’t load users.</span><button type="button" onClick={loadData}>Try again</button></div> : null}{usersState === 'empty' ? <div className="semantic-management-state"><span>No users are available to manage.</span></div> : null}{permissionsState === 'error' ? <div className="semantic-management-state is-error"><span>We couldn’t load permissions for this layer.</span><button type="button" onClick={loadData}>Try again</button></div> : null}{tablesState === 'error' ? <div className="semantic-management-state is-error"><span>We couldn’t load business tables for this layer.</span><button type="button" onClick={loadData}>Try again</button></div> : null}{usersState === 'ready' && permissionsState === 'ready' && tablesState === 'ready' ? <><div className="semantic-permission-user-picker"><label htmlFor="permission-user-search">User</label><input id="permission-user-search" value={userQuery} onChange={(event) => setUserQuery(event.target.value)} placeholder="Search by name or email" /><div className="semantic-permission-user-list">{visibleUsers.map((user) => <button type="button" key={user.userId} className={String(user.userId).toLowerCase() === String(selectedUserId).toLowerCase() ? 'selected' : ''} onClick={() => selectUser(user.userId)}><strong>{user.name}</strong><span>{user.email}</span></button>)}</div>{visibleUsers.length === 0 ? <small>No matching users.</small> : null}</div>{selectedUser ? <><div className="semantic-permission-selected"><div><strong>{selectedUser.name}</strong><span>{selectedUser.email}</span></div><b>{allowedCount} of {tables.length} tables allowed</b></div>{tables.length === 0 ? <div className="semantic-management-state"><span>No business tables are available for this layer.</span></div> : <><div className="semantic-permission-table-list">{tableRows.map((table) => <article key={table.name}><div><strong>{table.name}</strong><span>{table.description || (table.columnCount ? `${table.columnCount} columns` : 'Business table in this layer')}</span></div><label><input type="checkbox" checked={Boolean(table.isAllowed)} onChange={() => toggleTable(table.name)} /><span aria-hidden="true" />{table.isAllowed ? 'Allowed' : 'Denied'}</label></article>)}</div><div className="semantic-permission-savebar"><span>{hasUnsavedChanges ? 'You have unsaved changes.' : 'All changes are saved.'}</span><button type="button" className="primary" disabled={saving || !hasUnsavedChanges} onClick={saveChanges}>{saving ? 'Saving…' : 'Save changes'}</button></div></>}</> : null}</> : null}{notice ? <p className={`semantic-details-notice ${notice.type === 'error' ? 'is-error' : ''}`} role="status">{notice.text}</p> : null}</section>
}

function LayerBadges({ layer }) {
  return <div className="semantic-details-badges"><span className={layer.isActive ? 'is-active' : 'is-inactive'}><i aria-hidden="true" />{layer.isActive ? 'Active layer' : 'Inactive layer'}</span><span className={layer.hasApprovedRevision ? 'is-approved' : 'is-pending'}>{layer.hasApprovedRevision ? <IconCheck aria-hidden="true" /> : null}{layer.hasApprovedRevision ? 'Approved revision available' : 'No approved revision'}</span></div>
}

function DetailsLoading() {
  return <section className="semantic-details-state" aria-live="polite"><IconLoader className="copilot-processing-loader" aria-hidden="true" /><h2>Loading semantic layer</h2><p>Preparing this layer’s workspace.</p></section>
}

export default function AdminSemanticLayerDetails() {
  const { layerId, tab: routeTab } = useParams()
  const location = useLocation()
  const [layer, setLayer] = useState(null)
  const [status, setStatus] = useState(null)
  const [state, setState] = useState('loading')
  const [sourceFiles, setSourceFiles] = useState({})
  const [sourceState, setSourceState] = useState('idle')
  const [sourceAction, setSourceAction] = useState('')
  const [notice, setNotice] = useState(null)
  const [pendingDelete, setPendingDelete] = useState(null)
  const navigate = useNavigate()
  const tab = TABS.some((item) => item.key === routeTab) ? routeTab : 'overview'
  const uploadedFiles = useMemo(() => uploadedSourceFiles(normalizeSemanticSources(location.state?.uploadedSource)), [location.state])

  const loadLayer = useCallback(async () => {
    setState('loading')
    setNotice(null)
    try {
      let nextLayer = await getSemanticLayerById(layerId)
      const uploaded = location.state?.uploadedSource
      if (!nextLayer && uploaded) {
        nextLayer = {
          id: layerId,
          name: uploaded.name || uploaded.Name || 'New semantic layer',
          description: uploaded.description || uploaded.Description || '',
          databaseName: uploaded.databaseName || uploaded.DatabaseName || uploaded.name || uploaded.Name || '',
          isActive: false,
          hasApprovedRevision: false,
        }
      }
      setLayer(nextLayer)
      let nextStatus = null
      try {
        nextStatus = await getSemanticLayerStatus(layerId)
      } catch {
        nextStatus = null
      }
      setStatus(nextStatus)
      const persistedFiles = uploadedSourceFiles(normalizeSemanticSources(nextStatus || nextLayer))
      setSourceFiles((current) => ({ ...current, ...persistedFiles, ...uploadedFiles }))
      setState(nextLayer ? 'ready' : 'not-found')
    } catch {
      setState('error')
    }
  }, [layerId, uploadedFiles, location.state])

  useEffect(() => { Promise.resolve().then(loadLayer) }, [loadLayer])

  const sourceIds = useMemo(() => {
    const persistedSources = { ...(layer?.sources || {}), ...(status?.sources || {}) }
    return SOURCE_TYPES
      .map((type) => ({ key: type.key, fileId: persistedSources[type.sourceKey] }))
      .filter((source) => source.fileId)
  }, [layer, status])

  const loadSourceFiles = useCallback(async () => {
    if (!sourceIds.length) {
      setSourceState('ready')
      return
    }
    setSourceState('loading')
    try {
      const loaded = await Promise.allSettled(sourceIds.map(async (source) => [source.key, await getSemanticSourceFile(source.fileId)]))
      const successful = loaded.filter((result) => result.status === 'fulfilled').map((result) => result.value)
      setSourceFiles((current) => ({
        ...current,
        ...Object.fromEntries(successful.map(([key, file]) => [key, {
          fileId: file?.fileId || file?.FileId || file?.id || file?.Id,
          fileName: file?.fileName || file?.FileName || file?.name || file?.Name,
          fileType: file?.fileType || file?.FileType || file?.type,
          content: file?.content || file?.Content,
        }])),
      }))
      setSourceState('ready')
    } catch {
      setSourceState('ready')
    }
  }, [sourceIds])

  useEffect(() => {
    if (state === 'ready' && tab === 'sources') Promise.resolve().then(loadSourceFiles)
  }, [loadSourceFiles, state, tab])

  async function uploadSource(source, file) {
    setSourceAction(source.key)
    setNotice(null)
    try {
      const response = await upsertSemanticSourceFile({ layerId: layer.id, fileId: source.fileId, fileType: source.apiType, file })
      setSourceFiles((current) => ({ ...current, [source.key]: {
        fileId: response?.fileId || source.fileId,
        fileName: response?.fileName || file.name,
        fileType: response?.fileType || source.apiType,
        content: response?.content,
      } }))
      setStatus((current) => current ? { ...current, sources: { ...current.sources, [source.sourceKey]: response?.fileId || source.fileId } } : current)
      setNotice({ type: 'success', text: `${source.label} was saved successfully.` })
    } catch (error) {
      setNotice({ type: 'error', text: error.message || `We couldn’t save ${source.label.toLowerCase()}.` })
    } finally {
      setSourceAction('')
    }
  }

  async function downloadSource(source) {
    setSourceAction(`download:${source.key}`)
    setNotice(null)
    try {
      const { blob, fileName } = await getSemanticSourceFileContent(source.fileId)
      const downloadUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = downloadUrl
      anchor.download = fileName || source.fileName || `${source.key}-source`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(downloadUrl)
      setNotice({ type: 'success', text: `${source.label} is ready for download.` })
    } catch (error) {
      setNotice({ type: 'error', text: error.message || `We couldn’t prepare ${source.label.toLowerCase()} for download.` })
    } finally {
      setSourceAction('')
    }
  }

  async function removeSource() {
    if (!pendingDelete) return
    setSourceAction(pendingDelete.key)
    try {
      await deleteSemanticSourceFile(pendingDelete.fileId)
      setSourceFiles((current) => {
        const next = { ...current }
        delete next[pendingDelete.key]
        return next
      })
      setStatus((current) => current ? { ...current, sources: { ...current.sources, [pendingDelete.sourceKey]: null } } : current)
      setNotice({ type: 'success', text: `${pendingDelete.label} was removed.` })
      setPendingDelete(null)
    } catch (error) {
      setNotice({ type: 'error', text: error.message || `We couldn’t remove ${pendingDelete.label.toLowerCase()}.` })
      setPendingDelete(null)
    } finally {
      setSourceAction('')
    }
  }

  function handleDraftGenerated(response) {
    navigate(`/admin/semantic-layers/${layer.id}/revisions/${response.revisionId}/review`, {
      state: { generatedDraft: response, layerName: layer.name },
    })
  }

  return <main className="admin-shell">
    <AdminSidebar active="semantic" />
    <section className="admin-main semantic-details-main">
      <AdminTopBar title="Semantic Layer" description="Review and manage the business context used by Copilot." />
      {state === 'loading' ? <DetailsLoading /> : null}
      {state === 'error' ? <section className="semantic-details-state"><h2>We couldn’t load this layer</h2><p>Please check your connection and try again.</p><button type="button" className="primary" onClick={loadLayer}>Try again</button></section> : null}
      {state === 'not-found' ? <section className="semantic-details-state"><IconLayers aria-hidden="true" /><h2>Semantic layer not found</h2><p>This layer may have been removed or is no longer available.</p><Link className="primary" to="/admin/semantic-layers">Back to semantic layers</Link></section> : null}
      {state === 'ready' ? <>
        <Link className="semantic-details-back" to="/admin/semantic-layers"><IconArrowLeft aria-hidden="true" />All semantic layers</Link>
        <section className="semantic-details-hero">
          <div className="semantic-details-icon"><IconLayers aria-hidden="true" /></div>
          <div className="semantic-details-copy"><div className="semantic-details-title"><h2>{layer.name}</h2><LayerBadges layer={layer} /></div><p>{layer.description || 'No description provided for this semantic layer.'}</p><span><IconDatabase aria-hidden="true" />{layer.databaseName || 'Database not specified'}</span></div>
        </section>
        <nav className="semantic-details-tabs" aria-label="Semantic layer sections">{TABS.map((item) => <Link key={item.key} className={item.key === tab ? 'active' : ''} to={item.key === 'overview' ? `/admin/semantic-layers/${layer.id}` : `/admin/semantic-layers/${layer.id}/${item.key}`}>{item.label}</Link>)}</nav>
        {notice ? <p className={`semantic-details-notice ${notice.type === 'error' ? 'is-error' : ''}`} role="status">{notice.text}</p> : null}
        {tab === 'overview' ? <OverviewTab layer={layer} status={status} /> : null}
        {tab === 'sources' ? <SourcesTab layer={layer} status={status} sourceFiles={sourceFiles} sourceState={sourceState} actionKey={sourceAction} onDownload={downloadSource} onUpload={uploadSource} onDelete={setPendingDelete} /> : null}
        {tab === 'generate' ? <GenerateDraftTab layer={layer} status={status} sourceFiles={sourceFiles} onGenerated={handleDraftGenerated} /> : null}
        {tab === 'revisions' ? <RevisionsTab layer={layer} status={status} /> : null}
        {tab === 'tables' ? <TablesTab layer={layer} /> : null}
        {tab === 'permissions' ? <PermissionsTab layer={layer} /> : null}
      </> : null}
    </section>
    <ConfirmDialog open={Boolean(pendingDelete)} title="Remove source file?" message={`Remove the ${pendingDelete?.label || 'selected'} file from this semantic layer? This action cannot be undone.`} confirmLabel="Remove file" variant="destructive" isBusy={Boolean(sourceAction)} onConfirm={removeSource} onCancel={() => !sourceAction && setPendingDelete(null)} />
  </main>
}
