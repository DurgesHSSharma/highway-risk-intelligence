import { Link } from 'react-router-dom'
import RiskBadge from './RiskBadge'
import { formatDays, formatMonthLabel, formatNumber, formatPercent } from '../utils/format'

/** Purely presentational -- filtering/pagination state lives in the parent
 * (Analytics.jsx) so it can drive the real GET /analytics/risk-projects
 * request. Every row is a real scored project, never a hardcoded sample. */
export default function TopRiskTable({ items, startRank = 1 }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Project</th>
            <th>State</th>
            <th>Risk Level</th>
            <th>Risk Score</th>
            <th>Delay Risk</th>
            <th>Cost Risk</th>
            <th>Reporting Month</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => (
            <tr key={item.project_id}>
              <td>{startRank + i}</td>
              <td>
                <Link className="table-id" to={`/projects/${item.project_id}`}>
                  {item.project_id}
                </Link>
                <div className="muted" style={{ fontSize: 11 }}>
                  {item.project_name}
                </div>
              </td>
              <td>{item.state}</td>
              <td>
                <RiskBadge level={item.risk_level} />
              </td>
              <td>{formatNumber(item.risk_score, 1)}</td>
              <td>
                {formatPercent((item.significant_delay_probability ?? 0) * 100)} · {formatDays(item.final_delay_days_predicted)}
              </td>
              <td>
                {formatPercent((item.cost_overrun_probability ?? 0) * 100)} · {formatPercent(item.final_cost_overrun_pct_predicted)}
              </td>
              <td>{formatMonthLabel(item.reporting_month)}</td>
              <td>
                <span className="badge badge-info">Model-predicted</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
