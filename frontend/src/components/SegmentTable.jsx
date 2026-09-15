import { formatDays, formatNumber, formatPercent } from '../utils/format'

/** Renders one GET /analytics/segments response for a single dimension
 * (state / project_type / contractor). Historical and predicted columns
 * are visually grouped but never merged into one value -- and every
 * below-threshold row is still shown, just flagged, never dropped. */
export default function SegmentTable({ dimensionLabel, entries, minSampleThreshold }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>{dimensionLabel}</th>
            <th title={`Small-sample threshold: n < ${minSampleThreshold}`}>Sample</th>
            <th>Historical delay rate</th>
            <th>Historical cost-overrun rate</th>
            <th>Historical mean delay</th>
            <th>Predicted avg. delay prob.</th>
            <th>Predicted avg. cost prob.</th>
            <th>Predicted risk levels</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.value}>
              <td>
                {e.value}
                {e.small_sample && (
                  <span className="small-sample-tag" style={{ marginLeft: 6 }}>
                    Small sample
                  </span>
                )}
              </td>
              <td>{formatNumber(e.historical?.project_count ?? e.predicted?.scored_project_count ?? 0)}</td>
              <td>{e.historical ? formatPercent(e.historical.significant_delay_rate * 100) : '—'}</td>
              <td>{e.historical ? formatPercent(e.historical.cost_overrun_rate * 100) : '—'}</td>
              <td>{e.historical ? formatDays(e.historical.mean_final_delay_days) : '—'}</td>
              <td>{e.predicted ? formatPercent(e.predicted.avg_significant_delay_probability * 100) : '—'}</td>
              <td>{e.predicted ? formatPercent(e.predicted.avg_cost_overrun_probability * 100) : '—'}</td>
              <td style={{ fontSize: 11 }}>
                {e.predicted
                  ? Object.entries(e.predicted.risk_level_counts)
                      .map(([lvl, n]) => `${lvl[0]}${lvl.slice(1).toLowerCase()}: ${n}`)
                      .join(', ')
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
