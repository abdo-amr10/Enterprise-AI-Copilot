import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import AdminSidebar from '../components/AdminSidebar'
import AdminTopBar from '../components/AdminTopBar'
import ConfirmDialog from '../components/ConfirmDialog'
import { IconArrowLeft, IconCheck, IconLayers, IconLoader, IconX } from '../components/icons'
import { getSemanticRevision, reviewSemanticRevision } from '../services/semanticLayerService'
import '../styles/admin.css'
import '../styles/admin-pages.css'
import '../styles/semantic-layer-details.css'

function formatTimestamp(value) {
  const date = new Date(value)
  return value && !Number.isNaN(date.getTime()) ? date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'Not available'
}

function getCollectionCount(content, key) {
  const value = content?.[key] ?? content?.[key[0].toUpperCase() + key.slice(1)]
  return Array.isArray(value) ? value.length : 0
}

function isPending(status) {
  return String(status || '').replace(/\s/g, '').toLowerCase() === 'pendingreview'
}

export default function AdminSemanticDraftReview() {
  const { layerId, revisionId } = useParams()
  const navigate = useNavigate()
  const [revision, setRevision] = useState(null)
  const [state, setState] = useState('loading')
  const [comments, setComments] = useState('')
  const [pendingDecision, setPendingDecision] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [notice, setNotice] = useState(null)

  const loadRevision = useCallback(async () => {
    setState('loading')
    setNotice(null)
    try {
      setRevision(await getSemanticRevision(revisionId))
      setState('ready')
    } catch {
      setState('error')
    }
  }, [revisionId])

  useEffect(() => { Promise.resolve().then(loadRevision) }, [loadRevision])

  const contentSummary = useMemo(() => [
    ['Entities', getCollectionCount(revision?.content, 'entities')],
    ['Relationships', getCollectionCount(revision?.content, 'relationships')],
    ['Measures', getCollectionCount(revision?.content, 'measures')],
    ['Dimensions', getCollectionCount(revision?.content, 'dimensions')],
    ['Business rules', getCollectionCount(revision?.content, 'businessRules')],
  ], [revision])
  const validationIssues = getCollectionCount(revision?.content, 'validationIssues')
  const canReview = isPending(revision?.status)

  function requestDecision(decision) {
    setNotice(null)
    if (decision === 'Reject' && !comments.trim()) {
      setNotice({ type: 'error', text: 'Add a short reason before rejecting this revision.' })
      return
    }
    setPendingDecision(decision)
  }

  async function confirmDecision() {
    if (!pendingDecision) return
    setIsSubmitting(true)
    setNotice(null)
    try {
      const response = await reviewSemanticRevision({ semanticLayerId: layerId, revisionId, decision: pendingDecision, comments })
      setRevision((current) => ({ ...current, ...response, status: response?.status || (pendingDecision === 'Approve' ? 'Approved' : 'Rejected') }))
      setNotice({ type: 'success', text: pendingDecision === 'Approve' ? 'Revision approved. You can now activate this semantic layer when ready.' : 'Revision rejected. Update the data sources, then generate a new draft.' })
      setPendingDecision('')
    } catch (error) {
      setNotice({ type: 'error', text: error.message || 'We couldn’t save this review. Please try again.' })
      setPendingDecision('')
    } finally {
      setIsSubmitting(false)
    }
  }

  return <main className="admin-shell"><AdminSidebar active="semantic" /><section className="admin-main semantic-details-main"><AdminTopBar title="Review revision" description="Confirm that this business context is ready before making it available to Copilot." /><Link className="semantic-details-back" to={`/admin/semantic-layers/${layerId}/revisions`}><IconArrowLeft aria-hidden="true" />Back to revisions</Link>{state === 'loading' ? <section className="semantic-details-state"><IconLoader className="copilot-processing-loader" aria-hidden="true" /><h2>Loading revision</h2><p>Preparing the generated business context for review.</p></section> : null}{state === 'error' ? <section className="semantic-details-state"><IconLayers aria-hidden="true" /><h2>We couldn’t load this revision</h2><p>Please try again. If the problem continues, return to the layer and generate a new draft.</p><button type="button" className="primary" onClick={loadRevision}>Try again</button></section> : null}{state === 'ready' ? <section className="semantic-details-workspace semantic-draft-ready"><div className={`semantic-draft-ready-icon ${canReview ? '' : 'is-complete'}`}>{String(revision?.status || '').toLowerCase() === 'rejected' ? <IconX aria-hidden="true" /> : <IconCheck aria-hidden="true" />}</div><span className="semantic-details-kicker">{canReview ? 'Pending review' : revision?.status || 'Revision'}</span><h2>{canReview ? 'Review this semantic draft' : 'Revision review completed'}</h2><p>{canReview ? 'Review the generated business context, add an optional note, then approve or reject it.' : 'This revision has already received a decision and is kept as part of this layer’s change record.'}</p><div className="semantic-overview-grid"><div><small>REVISION</small><strong>{revision?.version || 'Draft'}</strong></div><div><small>STATUS</small><strong>{revision?.status || 'Pending review'}</strong></div><div><small>CREATED</small><strong>{formatTimestamp(revision?.buildTimestamp || revision?.createdAt)}</strong></div><div><small>GENERATION TYPE</small><strong>{revision?.lastRegenerationType || 'Not available'}</strong></div><div><small>VALIDATION NOTES</small><strong>{validationIssues ? `${validationIssues} item${validationIssues === 1 ? '' : 's'}` : 'No issues reported'}</strong></div><div><small>REVISION ID</small><strong>{revisionId}</strong></div></div><div className="semantic-review-content"><h3>Generated business context</h3><div>{contentSummary.map(([label, count]) => <span key={label}><strong>{count}</strong>{label}</span>)}</div></div>{canReview ? <><label className="semantic-review-comments">Review note <span>Optional for approval, required when rejecting</span><textarea value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Add context for this review" rows="4" /></label><div className="semantic-review-actions"><button type="button" className="semantic-review-reject" onClick={() => requestDecision('Reject')}>Reject revision</button><button type="button" className="primary" onClick={() => requestDecision('Approve')}>Approve revision</button></div></> : <div className="semantic-draft-ready-actions"><Link to="/admin/semantic-layers">Return to Semantic Layers</Link>{String(revision?.status || '').toLowerCase() === 'approved' ? <button className="primary" type="button" onClick={() => navigate('/admin/semantic-layers')}>Activate when ready</button> : <Link className="primary" to={`/admin/semantic-layers/${layerId}/sources`}>Update sources</Link>}</div>}{notice ? <p className={`semantic-details-notice ${notice.type === 'error' ? 'is-error' : ''}`} role="status">{notice.text}</p> : null}</section> : null}</section><ConfirmDialog open={Boolean(pendingDecision)} title={pendingDecision === 'Approve' ? 'Approve this revision?' : 'Reject this revision?'} message={pendingDecision === 'Approve' ? 'This marks the business context as approved. You can then activate its semantic layer when you are ready.' : 'This keeps the revision out of Copilot. You can update the sources and generate a new draft.'} confirmLabel={pendingDecision === 'Approve' ? 'Approve revision' : 'Reject revision'} variant={pendingDecision === 'Approve' ? 'primary' : 'destructive'} isBusy={isSubmitting} onConfirm={confirmDecision} onCancel={() => !isSubmitting && setPendingDecision('')} /></main>
}
