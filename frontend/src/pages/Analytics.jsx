import { useMemo } from 'react'
import { useApi } from '../hooks/useApi'
import { getPortfolioSummary } from '../api/endpoints'
import { useProjectsCache } from '../context/ProjectsCacheContext'
import AsyncSection from '../components/StateViews'
import DisclaimerBox from '../components/DisclaimerBox'
import OutcomeDonut from '../components/charts/OutcomeDonut'
import HorizontalBarList from '../components/charts/HorizontalBarList'
import { buildHistogram } from '../utils/histogram'
import { PALETTE } from '../utils/palette'
import { formatDays, formatNumber, formatPercent } from '../utils/format'

export default function Analytics() {
  const summary = useApi((signal) => getPortfolioSummary(signal), [])
  const { projects, status: projectsStatus } = useProjectsCache()

  const lengthHistogram = useMemo(() => buildHistogram(projects.map((p) => p.project_length_km), 100, ' km'), [projects])
  const contractHistogram = useMemo(
    () => buildHistogram(projects.map((p) => p.original_contract_value_inr_cr), 500, ' Cr'),
    [projects]
  )

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Analytics</h1>
          <p>Portfolio-wide statistics computed from the HRI backend — no fabricated trends or historical deltas.</p>
        </div>
      </div>

      <AsyncSection
        status={summary.status}
        error={summary.error}
        data={summary.data}
        onRetry={summary.reload}
        loadingLabel="Loading portfolio analytics…"
        errorTitle="Unable to load analytics."
      >
        {(data) => (
          <>
            <div className="grid kpi-grid">
              <div className="kpi-card">
                <div className="kpi-label">Total Projects</div>
                <div className="kpi-value">{formatNumber(data.total_projects)}</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-label">Avg. Final Delay</div>
                <div className="kpi-value" style={{ fontSize: 22 }}>{formatDays(data.avg_final_delay_days)}</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-label">Avg. Final Cost Overrun</div>
                <div className="kpi-value" style={{ fontSize: 22 }}>{formatPercent(data.avg_final_cost_overrun_pct)}</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-label">States Covered</div>
                <div className="kpi-value">{formatNumber(Object.keys(data.state_counts).length)}</div>
              </div>
            </div>

            <div className="grid two-col-grid">
              <div className="card card-padded">
                <div className="card-header">
                  <h2>Significant Delay Outcome</h2>
                </div>
                <OutcomeDonut
                  flaggedLabel="Significant delay"
                  flaggedCount={data.significant_delay_count}
                  totalProjects={data.total_projects}
                  color={PALETTE.red}
                />
              </div>
              <div className="card card-padded">
                <div className="card-header">
                  <h2>Cost Overrun Outcome</h2>
                </div>
                <OutcomeDonut
                  flaggedLabel="Cost overrun"
                  flaggedCount={data.cost_overrun_count}
                  totalProjects={data.total_projects}
                  color={PALETTE.amber}
                />
              </div>
            </div>

            <div className="card card-padded">
              <div className="card-header">
                <h2>Projects by State (all)</h2>
              </div>
              <HorizontalBarList
                data={Object.entries(data.state_counts)
                  .sort((a, b) => b[1] - a[1])
                  .map(([name, value]) => ({ name, value }))}
                height={Object.keys(data.state_counts).length * 26}
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

            <DisclaimerBox>{data.synthetic_data_disclaimer}</DisclaimerBox>
          </>
        )}
      </AsyncSection>

      <AsyncSection
        status={projectsStatus}
        data={projects}
        loadingLabel="Loading project distributions…"
        isEmpty={(d) => d.length === 0}
        emptyTitle="No project data available."
      >
        {() => (
          <div className="grid two-col-grid">
            <div className="card card-padded">
              <div className="card-header">
                <h2>Project Length Distribution</h2>
              </div>
              <HorizontalBarList data={lengthHistogram} color={PALETTE.blue} valueLabel="Projects" />
            </div>
            <div className="card card-padded">
              <div className="card-header">
                <h2>Contract Value Distribution</h2>
              </div>
              <HorizontalBarList data={contractHistogram} color={PALETTE.green} valueLabel="Projects" />
            </div>
          </div>
        )}
      </AsyncSection>
    </div>
  )
}
