import { formatDays, formatNumber, formatPercent } from '../../utils/format'
import { EmptyState } from '../StateViews'

/** Phase 15: one state/project_type/contractor peer-group card from
 * GET /projects/{id}/decision-intelligence's `peer_context`. Historical
 * and predicted stats are shown in clearly separate rows (never merged
 * into one ambiguous value, same convention as SegmentTable), and a
 * below-threshold peer group is still shown -- just flagged, never
 * dropped. An `unavailable` entry (missing project value, or the value
 * not appearing in the current segment report) renders an explicit,
 * honest empty state instead of fabricating a peer comparison. */
export default function PeerContextCard({ label, entry }) {
  if (!entry || entry.status !== 'ok') {
    return (
      <div className="card card-padded">
        <div className="card-header">
          <h2 style={{ fontSize: 13.5 }}>{label}</h2>
        </div>
        <EmptyState title="Peer context unavailable" message={entry?.reason} />
      </div>
    )
  }

  const { historical, predicted, small_sample: smallSample, min_sample_threshold: threshold, value } = entry

  return (
    <div className="card card-padded">
      <div className="card-header">
        <h2 style={{ fontSize: 13.5 }}>{label}</h2>
        {smallSample && <span className="small-sample-tag">Small sample</span>}
      </div>
      <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
        {value} · threshold n≥{threshold}
      </p>

      {historical ? (
        <div className="stack" style={{ gap: 6 }}>
          <div className="metric-row">
            <span>Historical sample</span>
            <span>{formatNumber(historical.project_count)} projects</span>
          </div>
          <div className="metric-row">
            <span>Historical significant-delay rate</span>
            <span>{formatPercent(historical.significant_delay_rate * 100)}</span>
          </div>
          <div className="metric-row">
            <span>Historical cost-overrun rate</span>
            <span>{formatPercent(historical.cost_overrun_rate * 100)}</span>
          </div>
          <div className="metric-row">
            <span>Historical mean delay</span>
            <span>{formatDays(historical.mean_final_delay_days)}</span>
          </div>
        </div>
      ) : (
        <EmptyState title="No historical data for this peer group." />
      )}

      {predicted ? (
        <div className="stack" style={{ gap: 6, marginTop: 10 }}>
          <div className="metric-row">
            <span>Predicted avg. delay probability</span>
            <span>{formatPercent(predicted.avg_significant_delay_probability * 100)}</span>
          </div>
          <div className="metric-row">
            <span>Predicted avg. cost-overrun probability</span>
            <span>{formatPercent(predicted.avg_cost_overrun_probability * 100)}</span>
          </div>
          <div className="metric-row">
            <span>Predicted risk levels</span>
            <span style={{ fontSize: 11 }}>
              {Object.entries(predicted.risk_level_counts)
                .map(([lvl, n]) => `${lvl[0]}${lvl.slice(1).toLowerCase()}: ${n}`)
                .join(', ')}
            </span>
          </div>
        </div>
      ) : (
        <p className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>
          Predicted (model-based) peer stats unavailable — the portfolio prediction cache has not been
          generated, or this peer group has no scored projects.
        </p>
      )}
    </div>
  )
}
