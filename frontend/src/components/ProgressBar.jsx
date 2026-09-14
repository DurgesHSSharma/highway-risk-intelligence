export default function ProgressBar({ label, value, planned }) {
  const clamp = (v) => Math.max(0, Math.min(100, v ?? 0))
  return (
    <div className="progress-row">
      <div className="progress-row-top">
        <span>{label}</span>
        <span>
          {value == null ? '—' : `${value.toFixed(1)}%`}
          {planned != null && <span className="muted"> / planned {planned.toFixed(1)}%</span>}
        </span>
      </div>
      <div className="progress-track">
        {planned != null && <div className="progress-fill planned" style={{ width: `${clamp(planned)}%` }} />}
        {value != null && (
          <div className="progress-fill" style={{ width: `${clamp(value)}%`, opacity: 0.85 }} />
        )}
      </div>
    </div>
  )
}
