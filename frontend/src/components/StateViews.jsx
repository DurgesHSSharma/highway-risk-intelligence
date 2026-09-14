import { IconAlertTriangle, IconInfo, IconRefresh } from './icons'

export function LoadingState({ label = 'Loading…' }) {
  return (
    <div className="state-block compact" role="status" aria-live="polite">
      <span className="spinner" />
      <span className="state-desc">{label}</span>
    </div>
  )
}

export function ErrorState({
  title = 'Unable to load data.',
  message,
  onRetry,
}) {
  return (
    <div className="state-block compact" role="alert">
      <span className="state-icon">
        <IconAlertTriangle size={26} />
      </span>
      <span className="state-title">{title}</span>
      {message && <span className="state-desc">{message}</span>}
      {onRetry && (
        <button type="button" className="btn btn-sm" onClick={onRetry}>
          <IconRefresh size={14} /> Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title = 'Nothing to show yet.', message, icon }) {
  return (
    <div className="state-block compact">
      <span className="state-icon">{icon || <IconInfo size={26} />}</span>
      <span className="state-title">{title}</span>
      {message && <span className="state-desc">{message}</span>}
    </div>
  )
}

/**
 * Standard wrapper for the loading / error / empty / success sequence that
 * every API-driven section needs. `isEmpty(data)` decides the empty state;
 * omit it to skip the empty check entirely.
 */
export default function AsyncSection({
  status,
  error,
  data,
  onRetry,
  loadingLabel,
  errorTitle,
  isEmpty,
  emptyTitle,
  emptyMessage,
  emptyIcon,
  children,
}) {
  if (status === 'loading' || status === 'idle') return <LoadingState label={loadingLabel} />
  if (status === 'error') {
    return <ErrorState title={errorTitle} message={error?.message} onRetry={onRetry} />
  }
  if (isEmpty && isEmpty(data)) {
    return <EmptyState title={emptyTitle} message={emptyMessage} icon={emptyIcon} />
  }
  return children(data)
}
