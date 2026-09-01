export default function ConfirmDialog({ open, title, message, confirmLabel, variant = 'primary', onConfirm, onCancel }) {
  if (!open) return null
  return <div className="confirm-dialog-backdrop" role="presentation"><section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title"><h2 id="confirm-dialog-title">{title}</h2><p>{message}</p><div className="confirm-dialog-actions"><button type="button" onClick={onCancel}>Cancel</button><button className={variant === 'destructive' ? 'is-destructive' : 'primary'} type="button" onClick={onConfirm}>{confirmLabel}</button></div></section></div>
}
