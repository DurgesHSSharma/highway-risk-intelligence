import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { getPortfolioSummary } from '../api/endpoints'
import { useProjectsCache } from '../context/ProjectsCacheContext'
import KpiCard from '../components/KpiCard'
import AsyncSection from '../components/StateViews'
import DisclaimerBox from '../components/DisclaimerBox'
import RiskBadge from '../components/RiskBadge'
import OutcomeDonut from '../components/charts/OutcomeDonut'
import HorizontalBarList from '../components/charts/HorizontalBarList'
import { IconAlertTriangle, IconProjects, IconRisk, IconDashboard as IconOngoing } from '../components/icons'
import { formatNumber, formatDays, formatPercent } from '../utils/format'
import { PALETTE } from '../utils/palette'

export default function Dashboard() {
  const summary = useApi((signal) => getPortfolioSummary(signal), [])
  const { projects, status: projectsStatus, error: projectsError, reload: reloadProjects } = useProjectsCache()

  const sampleProjects = useMemo(() => projects.slice(0, 6), [projects])

  return (
    <div className="stack">
      <div className="hero">
        <h1>AI-Powered Highway Project Intelligence</h1>
        <p>Predicting delays. Controlling costs. Enabling data-driven decisions for highway infrastructure portfolios.</p>
      </div>

      <AsyncSection
        status={summary.status}
        error={summary.error}
        data={summary.data}
        onRetry={summary.reload}
        loadingLabel="Loading portfolio summary…"
        errorTitle="Unable to load portfolio KPIs."
      >
        {(data) => (
          <>
            <div className="grid kpi-grid">
              <KpiCard
                icon={<IconProjects size={18} />}
                tone="navy"
                label="Total Projects"
                value={formatNumber(data.total_projects)}
                note="All projects in the synthetic portfolio"
              />
              <KpiCard
                icon={<IconOngoing size={18} />}
                tone="blue"
                label="Ongoing Projects"
                value={formatNumber(data.status_counts.Ongoing || 0)}
                note={
                  !data.status_counts.Ongoing
                    ? 'Every project in this dataset reaches "Completed" at its latest recorded snapshot'
                    : `${formatNumber(data.status_counts.Completed || 0)} completed`
                }
              />
              <KpiCard
                icon={<IconAlertTriangle size={18} />}
                tone="red"
                label="Significant Delay (flagged)"
                value={formatNumber(data.significant_delay_count)}
                note={`${formatPercent((data.significant_delay_count / data.total_projects) * 100)} of portfolio`}
              />
              <KpiCard
                icon={<IconRisk size={18} />}
                tone="amber"
                label="Cost Overrun (flagged)"
                value={formatNumber(data.cost_overrun_count)}
                note={`${formatPercent((data.cost_overrun_count / data.total_projects) * 100)} of portfolio`}
              />
            </div>

            <div className="grid two-col-grid">
              <div className="card card-padded">
                <div className="card-header">
                  <h2>Delay Outcome Distribution</h2>
                  <RiskBadge level="high" label="significant_delay" />
                </div>
                <OutcomeDonut
                  flaggedLabel="Significant delay"
                  flaggedCount={data.significant_delay_count}
                  totalProjects={data.total_projects}
                  color={PALETTE.red}
                />
                <p className="muted" style={{ fontSize: 11.5, marginTop: 14, marginBottom: 0 }}>
                  Recorded final <code>significant_delay</code> outcome across the portfolio, avg.{' '}
                  {formatDays(data.avg_final_delay_days)} final delay.
                </p>
              </div>
              <div className="card card-padded">
                <div className="card-header">
                  <h2>Cost Overrun Distribution</h2>
                  <RiskBadge level="medium" label="cost_overrun" />
                </div>
                <OutcomeDonut
                  flaggedLabel="Cost overrun"
                  flaggedCount={data.cost_overrun_count}
                  totalProjects={data.total_projects}
                  color={PALETTE.amber}
                />
                <p className="muted" style={{ fontSize: 11.5, marginTop: 14, marginBottom: 0 }}>
                  Recorded final <code>cost_overrun</code> outcome, avg.{' '}
                  {formatPercent(data.avg_final_cost_overrun_pct)} final cost overrun.
                </p>
              </div>
            </div>

            <div className="grid two-col-grid">
              <div className="card card-padded">
                <div className="card-header">
                  <h2>Projects by State</h2>
                </div>
                <HorizontalBarList
                  data={Object.entries(data.state_counts)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 8)
                    .map(([name, value]) => ({ name, value }))}
                />
              </div>
              <div className="card card-padded">
                <div className="card-header">
                  <h2>Project Type Distribution</h2>
                </div>
                <HorizontalBarList
                  data={Object.entries(data.project_type_counts)
                    .sort((a, b) => b[1] - a[1])
                    .map(([name, value]) => ({ name, value }))}
                  color={PALETTE.navy}
                />
              </div>
            </div>

            <DisclaimerBox>{data.synthetic_data_disclaimer}</DisclaimerBox>
          </>
        )}
      </AsyncSection>

      <div className="card card-padded">
        <div className="card-header">
          <h2>Sample Projects</h2>
          <Link className="link" to="/projects">
            View all projects
          </Link>
        </div>
        <AsyncSection
          status={projectsStatus}
          error={projectsError}
          data={sampleProjects}
          onRetry={reloadProjects}
          loadingLabel="Loading projects…"
          errorTitle="Unable to load projects."
          isEmpty={(d) => d.length === 0}
          emptyTitle="No projects found."
        >
          {(list) => (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Project ID</th>
                    <th>Project Name</th>
                    <th>State</th>
                    <th>Type</th>
                    <th>Length (km)</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((p) => (
                    <tr key={p.project_id}>
                      <td>
                        <Link className="table-id" to={`/projects/${p.project_id}`}>
                          {p.project_id}
                        </Link>
                      </td>
                      <td>{p.project_name}</td>
                      <td>{p.state}</td>
                      <td>{p.project_type}</td>
                      <td>{formatNumber(p.project_length_km, 1)}</td>
                      <td>
                        <RiskBadge level={p.current_status === 'Completed' ? 'low' : 'medium'} label={p.current_status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncSection>
      </div>
    </div>
  )
}
