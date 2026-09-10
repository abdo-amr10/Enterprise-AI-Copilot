import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AdminSidebar from '../components/AdminSidebar'
import AdminTopBar from '../components/AdminTopBar'
import ConfirmDialog from '../components/ConfirmDialog'
import SchemaDiagram from '../components/SchemaDiagram'
import { IconArrowLeft, IconCheck, IconDownload, IconLayers, IconLoader, IconX } from '../components/icons'
import { activateSemanticLayer, getSemanticRevision, getSemanticRevisionSchemaFile, reviewSemanticRevision } from '../services/semanticLayerService'
import { parseSchemaDocument } from '../utils/schemaDiagram'
import '../styles/admin.css'
import '../styles/admin-pages.css'
import '../styles/semantic-layer-details.css'

function formatTimestamp(value) { const date = new Date(value); return value && !Number.isNaN(date.getTime()) ? date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'Not available' }
function getCollectionCount(content, key) { const value = content?.[key] ?? content?.[key[0].toUpperCase() + key.slice(1)]; return Array.isArray(value) ? value.length : 0 }
function isPending(status) { return String(status || '').replace(/\s/g, '').toLowerCase() === 'pendingreview' }
function getCollection(content, key) { const value = content?.[key] ?? content?.[key[0].toUpperCase() + key.slice(1)]; return Array.isArray(value) ? value : [] }
function valueOrDash(value) { return value === null || value === undefined || value === '' ? '—' : String(value) }

function ReviewObjectCard({ item, fields }) {
  return <article className="semantic-review-object-card"><div className="semantic-review-object-title"><strong>{valueOrDash(item?.name || item?.id)}</strong>{item?.generated === true ? <span>AI generated</span> : null}</div><div className="semantic-review-object-fields">{fields.map(([label, value]) => <div key={label}><small>{label}</small><span>{valueOrDash(value)}</span></div>)}</div></article>
}

function GeneratedContext({ content }) {
  const sections = [
    { key: 'entities', title: 'Entities', fields: (item) => [['Mapping', item.mapping], ['Source table', item.source_table], ['Grain', item.grain || item.natural_grain], ['Primary identifier', item.primary_identifier], ['Security scope', item.security_scope], ['Description', item.description]] },
    { key: 'measures', title: 'Measures', fields: (item) => [['Mapping', item.mapping], ['Aggregation', item.aggregation || item.aggregation_function], ['Business definition', item.business_definition], ['Source', item.source_table ? `${item.source_table}.${item.source_column || '—'}` : item.source], ['Description', item.description]] },
    { key: 'dimensions', title: 'Dimensions', fields: (item) => [['Mapping', item.mapping], ['Grain', item.grain || item.natural_grain], ['Source', item.source], ['Description', item.description]] },
    { key: 'businessRules', title: 'Business rules', fields: (item) => [['Rule type', item.rule_type], ['Enforcement', item.enforcement], ['Source', item.source], ['Description', item.description]] },
    { key: 'relationships', title: 'Relationships', fields: (item) => [['From', item.from_table && item.from_column ? `${item.from_table}.${item.from_column}` : item.source?.table], ['To', item.to_table && item.to_column ? `${item.to_table}.${item.to_column}` : item.target?.table], ['Type', item.relationship_type], ['Cardinality', item.cardinality], ['Status', item.status], ['Join types', Array.isArray(item.allowed_join_types) ? item.allowed_join_types.join(', ') : item.allowed_join_types], ['Description', item.description]] },
    { key: 'validationIssues', title: 'Validation issues', fields: (item) => [['Details', typeof item === 'object' ? item.message || item.description || JSON.stringify(item) : item]] },
  ]

  return <section className="semantic-generated-context"><h3>Generated business context</h3><div className="semantic-review-context-sections">{sections.map(({ key, title, fields }) => { const items = getCollection(content, key); return <section className="semantic-review-context-section" key={key}><div className="semantic-review-context-heading"><strong>{title}</strong><span>{items.length}</span></div>{items.length ? <div className="semantic-review-object-grid">{items.map((item, index) => <ReviewObjectCard key={item?.object_id || item?.id || `${key}-${index}`} item={item} fields={fields(item)} />)}</div> : <p className="semantic-review-context-empty">No {title.toLowerCase()} found.</p>}</section> })}</div></section>
}

export default function AdminSemanticDraftReview() {
  const { layerId, revisionId } = useParams()
  const [revision, setRevision] = useState(null)
  const [state, setState] = useState('loading')
  const [comments, setComments] = useState('')
  const [pendingDecision, setPendingDecision] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [notice, setNotice] = useState(null)
  const [schemaState, setSchemaState] = useState('idle')
  const [schemaModel, setSchemaModel] = useState(null)
  const [schemaBlob, setSchemaBlob] = useState(null)
  const [schemaFileName, setSchemaFileName] = useState('schema.json')
  const [isActivationConfirming, setIsActivationConfirming] = useState(false)
  const [activationState, setActivationState] = useState('idle')
  const schemaDiagramRef = useRef(null)

  const loadRevision = useCallback(async () => {
    setState('loading'); setSchemaState('loading'); setNotice(null)
    try {
      const nextRevision = await getSemanticRevision(revisionId)
      setRevision(nextRevision); setSchemaModel(null); setSchemaBlob(null); setState('ready')
      try {
        const schemaFile = await getSemanticRevisionSchemaFile(nextRevision?.semanticLayerId)
        if (!schemaFile.fileId || !schemaFile.blob) { setSchemaState('missing'); return }
        const fileName = schemaFile.fileName || 'schema.json'
        setSchemaFileName(fileName); setSchemaBlob(schemaFile.blob)
        if (!/\.json$/i.test(fileName)) { setSchemaState('unsupported'); return }
        let document = null
        try { document = JSON.parse(await schemaFile.blob.text()) } catch { document = null }
        const model = document ? parseSchemaDocument(document) : null
        if (!model || !model.tables.length) setSchemaState('invalid')
        else { setSchemaModel(model); setSchemaState('ready') }
      } catch { setSchemaState('error') }
    } catch { setState('error') }
  }, [revisionId])

  useEffect(() => { Promise.resolve().then(loadRevision) }, [loadRevision])
  const contentSummary = useMemo(() => [['Entities', getCollectionCount(revision?.content, 'entities')], ['Relationships', getCollectionCount(revision?.content, 'relationships')], ['Measures', getCollectionCount(revision?.content, 'measures')], ['Dimensions', getCollectionCount(revision?.content, 'dimensions')], ['Business rules', getCollectionCount(revision?.content, 'businessRules')]], [revision])
  const validationIssues = getCollectionCount(revision?.content, 'validationIssues')
  const canReview = isPending(revision?.status)

  function requestDecision(decision) { setNotice(null); if (decision === 'Reject' && !comments.trim()) { setNotice({ type: 'error', text: 'Add a short reason before rejecting this revision.' }); return } setPendingDecision(decision) }
  async function confirmDecision() {
    if (!pendingDecision) return
    setIsSubmitting(true); setNotice(null)
    try { const response = await reviewSemanticRevision({ semanticLayerId: layerId, revisionId, decision: pendingDecision, comments }); setRevision((current) => ({ ...current, ...response, status: response?.status || (pendingDecision === 'Approve' ? 'Approved' : 'Rejected') })); setNotice({ type: 'success', text: pendingDecision === 'Approve' ? 'Revision approved. You can now activate this semantic layer when ready.' : 'Revision rejected. Update the data sources, then generate a new draft.' }); setPendingDecision('') } catch (error) { setNotice({ type: 'error', text: error.message || 'We couldn’t save this review. Please try again.' }); setPendingDecision('') } finally { setIsSubmitting(false) }
  }
  function downloadOriginalSchema() { if (!schemaBlob) { setNotice({ type: 'error', text: 'The original schema file is not available for download.' }); return } const url = URL.createObjectURL(schemaBlob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = schemaFileName; document.body.appendChild(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 0) }
  function downloadSchemaDiagram() { if (!schemaDiagramRef.current) { setNotice({ type: 'error', text: 'The schema diagram is not available for download.' }); return } schemaDiagramRef.current.download() }
  async function activateLayer() { if (!layerId || activationState === 'loading') return; setActivationState('loading'); setNotice(null); try { await activateSemanticLayer(layerId); setActivationState('active'); setNotice({ type: 'success', text: 'This semantic layer is now active and available to Copilot.' }); setIsActivationConfirming(false) } catch (error) { setActivationState('error'); setNotice({ type: 'error', text: error.message || 'We couldn’t activate this semantic layer. Please try again.' }); setIsActivationConfirming(false) } }

  return <main className="admin-shell"><AdminSidebar active="semantic" /><section className="admin-main semantic-details-main"><AdminTopBar title="Review revision" description="Confirm that this business context is ready before making it available to Copilot." /><Link className="semantic-details-back" to={`/admin/semantic-layers/${layerId}/revisions`}><IconArrowLeft aria-hidden="true" />Back to revisions</Link>{state === 'loading' ? <section className="semantic-details-state"><IconLoader className="copilot-processing-loader" aria-hidden="true" /><h2>Loading revision</h2><p>Preparing the generated business context for review.</p></section> : null}{state === 'error' ? <section className="semantic-details-state"><IconLayers aria-hidden="true" /><h2>We couldn’t load this revision</h2><p>Please try again. If the problem continues, return to the layer and generate a new draft.</p><button type="button" className="primary" onClick={loadRevision}>Try again</button></section> : null}{state === 'ready' ? <section className="semantic-details-workspace semantic-draft-ready"><div className={`semantic-draft-ready-icon ${canReview ? '' : 'is-complete'}`}>{String(revision?.status || '').toLowerCase() === 'rejected' ? <IconX aria-hidden="true" /> : <IconCheck aria-hidden="true" />}</div><span className="semantic-details-kicker">{canReview ? 'Pending review' : revision?.status || 'Revision'}</span><h2>{canReview ? 'Review this semantic draft' : 'Revision review completed'}</h2><p>{canReview ? 'Review the generated business context, add an optional note, then approve or reject it.' : 'This revision has already received a decision and is kept as part of this layer’s change record.'}</p><div className="semantic-overview-grid"><div><small>REVISION</small><strong>{revision?.version || 'Draft'}</strong></div><div><small>STATUS</small><strong>{revision?.status || 'Pending review'}</strong></div><div><small>CREATED</small><strong>{formatTimestamp(revision?.buildTimestamp || revision?.createdAt)}</strong></div><div><small>GENERATION TYPE</small><strong>{revision?.lastRegenerationType || 'Not available'}</strong></div><div><small>VALIDATION NOTES</small><strong>{validationIssues ? `${validationIssues} item${validationIssues === 1 ? '' : 's'}` : 'No issues reported'}</strong></div><div><small>REVISION ID</small><strong>{revisionId}</strong></div></div><section className="semantic-schema-panel"><div className="semantic-schema-heading"><div><span className="semantic-details-kicker">Schema definition</span><h3>Source schema</h3><p>The diagram is generated from the original schema file saved for this revision.</p></div><div className="semantic-schema-actions"><button type="button" onClick={downloadOriginalSchema} disabled={!schemaBlob}><IconDownload aria-hidden="true" />Original file</button><button type="button" onClick={downloadSchemaDiagram} disabled={schemaState !== 'ready'}><IconDownload aria-hidden="true" />Download diagram</button></div></div>{schemaState === 'loading' ? <div className="semantic-schema-state"><IconLoader className="copilot-processing-loader" aria-hidden="true" />Loading the saved schema…</div> : null}{schemaState === 'missing' ? <div className="semantic-schema-state"><IconLayers aria-hidden="true" /><strong>No schema file is linked to this revision.</strong><span>The revision metadata is available, but the backend did not return a schema file reference.</span></div> : null}{schemaState === 'unsupported' ? <div className="semantic-schema-state"><IconLayers aria-hidden="true" /><strong>{schemaFileName} is not a JSON schema.</strong><span>You can download the original file, but an interactive ER diagram requires a JSON schema.</span></div> : null}{schemaState === 'invalid' ? <div className="semantic-schema-state is-error"><IconX aria-hidden="true" /><strong>The saved schema could not be read as a valid diagram.</strong><span>The original file is still available for download.</span></div> : null}{schemaState === 'error' ? <div className="semantic-schema-state is-error"><IconX aria-hidden="true" /><strong>We couldn’t load the saved schema.</strong><span>Try again later or download it from Data Sources.</span></div> : null}{schemaState === 'ready' ? <SchemaDiagram ref={schemaDiagramRef} schema={schemaModel} /> : null}</section><div className="semantic-review-content"><h3>Generated business context</h3><div>{contentSummary.map(([label, count]) => <span key={label}><strong>{count}</strong>{label}</span>)}</div></div><GeneratedContext content={revision?.content} />{canReview ? <><label className="semantic-review-comments">Review note <span>Optional for approval, required when rejecting</span><textarea value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Add context for this review" rows="4" /></label><div className="semantic-review-actions"><button type="button" className="semantic-review-reject" onClick={() => requestDecision('Reject')}>Reject revision</button><button type="button" className="primary" onClick={() => requestDecision('Approve')}>Approve revision</button></div></> : <div className="semantic-draft-ready-actions"><Link to="/admin/semantic-layers">Return to Semantic Layers</Link>{String(revision?.status || '').toLowerCase() === 'approved' ? <button className="primary" type="button" disabled={activationState === 'loading' || activationState === 'active'} onClick={() => setIsActivationConfirming(true)}>{activationState === 'loading' ? 'Activating…' : activationState === 'active' ? 'Active layer' : 'Activate when ready'}</button> : <Link className="primary" to={`/admin/semantic-layers/${layerId}/sources`}>Update sources</Link>}</div>}{notice ? <p className={`semantic-details-notice ${notice.type === 'error' ? 'is-error' : ''}`} role="status">{notice.text}</p> : null}</section> : null}</section><ConfirmDialog open={Boolean(pendingDecision)} title={pendingDecision === 'Approve' ? 'Approve this revision?' : 'Reject this revision?'} message={pendingDecision === 'Approve' ? 'This marks the business context as approved. You can then activate this semantic layer when you are ready.' : 'This keeps the revision out of Copilot. You can update the sources and generate a new draft.'} confirmLabel={pendingDecision === 'Approve' ? 'Approve revision' : 'Reject revision'} variant={pendingDecision === 'Approve' ? 'primary' : 'destructive'} isBusy={isSubmitting} onConfirm={confirmDecision} onCancel={() => !isSubmitting && setPendingDecision('')} /><ConfirmDialog open={isActivationConfirming} title="Activate this semantic layer?" message="This will make the approved business context the one used by Copilot. Any other active semantic layer will be deactivated." confirmLabel={activationState === 'loading' ? 'Activating…' : 'Activate layer'} variant="primary" isBusy={activationState === 'loading'} onConfirm={activateLayer} onCancel={() => activationState !== 'loading' && setIsActivationConfirming(false)} /></main>
}
