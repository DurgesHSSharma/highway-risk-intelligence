import RiskBadge, { riskLevelFromProbability } from './RiskBadge'
import { formatDays, formatPercent } from '../utils/format'

export function ProbabilityTile({ title, statusLabel, probability, predictedClass, actualValue, isActual, summaryText }) {
  let level = null
  let valueLabel
  if (isActual) {
    level = actualValue ? 'high' : 'low'
    valueLabel = actualValue ? 'Yes' : 'No'
  } else if (probability != null) {
    level = riskLevelFromProbability(probability)
    valueLabel = formatPercent(probability * 100)
  }

  return (
    <div className="kpi-card">
      <div className="kpi-label">{title}</div>
      <div className="kpi-value" style={{ fontSize: 22 }}>
        {valueLabel ?? '—'}
      </div>
      {level && <RiskBadge level={level} />}
      {!isActual && predictedClass != null && (
        <div className="kpi-note">Predicted class: {predictedClass ? 'Delay/Overrun' : 'No delay/overrun'}</div>
      )}
      {statusLabel && <div className="kpi-note">{statusLabel}</div>}
      {summaryText && (
        <p className="muted" style={{ fontSize: 11.5, margin: 0 }}>
          {summaryText}
        </p>
      )}
    </div>
  )
}

export function RegressionTile({ title, value, unit, statusLabel, summaryText }) {
  return (
    <div className="kpi-card">
      <div className="kpi-label">{title}</div>
      <div className="kpi-value" style={{ fontSize: 22 }}>
        {value == null ? '—' : unit === 'days' ? formatDays(value) : formatPercent(value)}
      </div>
      {statusLabel && <div className="kpi-note">{statusLabel}</div>}
      {summaryText && (
        <p className="muted" style={{ fontSize: 11.5, margin: 0 }}>
          {summaryText}
        </p>
      )}
    </div>
  )
}
