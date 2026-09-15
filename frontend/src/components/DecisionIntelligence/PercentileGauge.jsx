import RiskBadge from '../RiskBadge'
import { formatNumber } from '../../utils/format'

/** Phase 15: renders this project's portfolio-relative percentile as a
 * horizontal position marker (reusing the existing .progress-track/
 * .progress-fill tokens), paired with the portfolio-relative risk-level
 * badge and cohort size -- never color alone (RiskBadge already pairs a
 * dot + text). */
export default function PercentileGauge({ percentile, riskLevel, cohortSize }) {
  const clamped = Math.max(0, Math.min(100, percentile ?? 0))
  return (
    <div>
      <div className="progress-row-top">
        <span>Portfolio percentile</span>
        <span>
          <strong>{formatNumber(percentile, 1)}th</strong> percentile of {formatNumber(cohortSize)} scored projects
        </span>
      </div>
      <div className="progress-track" style={{ height: 10 }}>
        <div className="progress-fill" style={{ width: `${clamped}%`, opacity: 0.85 }} />
      </div>
      <div style={{ marginTop: 8 }}>
        {riskLevel && <RiskBadge level={riskLevel} />}
      </div>
    </div>
  )
}
