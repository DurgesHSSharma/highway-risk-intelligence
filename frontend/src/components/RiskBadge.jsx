// Risk status is always shown as color + icon + text together (never color
// alone), per the accessibility requirement that color must not be the
// only signal.

const LEVELS = {
  critical: { className: 'badge-critical', label: 'Critical' },
  high: { className: 'badge-high', label: 'High' },
  medium: { className: 'badge-medium', label: 'Medium' },
  low: { className: 'badge-low', label: 'Low' },
}

export default function RiskBadge({ level, label }) {
  const normalized = String(level || '').toLowerCase()
  const config = LEVELS[normalized] || { className: 'badge-neutral', label: label || level || 'Unknown' }
  return (
    <span className={`badge ${config.className}`}>
      <span className="badge-dot" aria-hidden="true" />
      {label || config.label}
    </span>
  )
}

/** Buckets a 0-1 probability into the same high/medium/low vocabulary used
 * throughout the app. Thresholds are simple, disclosed, and applied
 * uniformly -- not tuned per screen. */
export function riskLevelFromProbability(probability) {
  if (probability == null || Number.isNaN(probability)) return null
  if (probability >= 0.6) return 'high'
  if (probability >= 0.3) return 'medium'
  return 'low'
}
