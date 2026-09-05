export default function ConfirmDialog({ open, title, message, confirmLabel, variant = 'primary', isBusy = false, onConfirm, onCancel }) {
  if (!open) return null
  return <div className="confirm-dialog-backdrop" role="presentation"><section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title"><h2 id="confirm-dialog-title">{title}</h2><p>{message}</p><div className="confirm-dialog-actions"><button type="button" disabled={isBusy} onClick={onCancel}>Cancel</button><button className={variant === 'destructive' ? 'is-destructive' : 'primary'} type="button" disabled={isBusy} onClick={onConfirm}>{isBusy ? 'Working…' : confirmLabel}</button></div></section></div>
}
