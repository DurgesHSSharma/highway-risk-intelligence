import { useMemo, useState } from 'react'
import { useApi } from '../hooks/useApi'
import {
  getPortfolioDrivers,
  getPortfolioOverview,
  getPortfolioSegments,
  getPortfolioSummary,
  getPortfolioTrends,
  getRiskProjects,
} from '../api/endpoints'
import { useProjectsCache } from '../context/ProjectsCacheContext'
import AsyncSection from '../components/StateViews'
import DisclaimerBox from '../components/DisclaimerBox'
import SourceLabel from '../components/SourceLabel'
import RiskBadge from '../components/RiskBadge'
import DriverBar from '../components/DriverBar'
import TopRiskTable from '../components/TopRiskTable'
import SegmentTable from '../components/SegmentTable'
import OutcomeDonut from '../components/charts/OutcomeDonut'
import HorizontalBarList from '../components/charts/HorizontalBarList'
import RiskMatrixChart from '../components/charts/RiskMatrixChart'
import TrendLineChart from '../components/charts/TrendLineChart'
import { buildHistogram } from '../utils/histogram'
import { PALETTE } from '../utils/palette'
import { formatDate, formatDays, formatNumber, formatPercent } from '../utils/format'

const RISK_LEVELS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

const DIMENSIONS = [
  { key: 'state', label: 'State' },
  { key: 'project_type', label: 'Project Type' },
  { key: 'contractor', label: 'Contractor' },
]

const TASK_LABELS = {
  significant_delay: 'Significant Delay Probability',
  final_delay_days: 'Predicted Delay Days',
  cost_overrun: 'Cost Overrun Probability',
  final_cost_overrun_pct: 'Predicted Cost Overrun %',
}

export default function Analytics() {
  const summary = useApi((signal) => getPortfolioSummary(signal), [])
  const { projects, status: projectsStatus } = useProjectsCache()

  const overview = useApi((signal) => getPortfolioOverview(signal), [])
  const drivers = useApi((signal) => getPortfolioDrivers(signal), [])
  const trends = useApi((signal) => getPortfolioTrends(signal), [])

  const [riskFilters, setRiskFilters] = useState({ state: '', project_type: '', risk_level: '' })
  const riskProjects = useApi(
    (signal) =>
      getRiskProjects(
        {
          state: riskFilters.state || undefined,
          project_type: riskFilters.project_type || undefined,
          risk_level: riskFilters.risk_level || undefined,
          limit: 15,
        },
        signal
      ),
    [riskFilters.state, riskFilters.project_type, riskFilters.risk_level]
  )

  // Separate, higher-limit fetch for the Risk Matrix scatter -- the Top
  // Risk table intentionally shows only the top 15, which would make a
  // near-empty, meaningless scatter plot. Same filters, same endpoint,
  // just a larger page (backend's max page size) so the matrix reflects a
  // representative slice of the whole matching cohort.
  const riskMatrix = useApi(
    (signal) =>
      getRiskProjects(
        {
          state: riskFilters.state || undefined,
          project_type: riskFilters.project_type || undefined,
          risk_level: riskFilters.risk_level || undefined,
          limit: 100,
        },
        signal
      ),
    [riskFilters.state, riskFilters.project_type, riskFilters.risk_level]
  )

  const [segmentDimension, setSegmentDimension] = useState('state')
  const segments = useApi((signal) => getPortfolioSegments(segmentDimension, signal), [segmentDimension])

  const lengthHistogram = useMemo(() => buildHistogram(projects.map((p) => p.project_length_km), 100, ' km'), [projects])
  const contractHistogram = useMemo(
    () => buildHistogram(projects.map((p) => p.original_contract_value_inr_cr), 500, ' Cr'),
    [projects]
  )
  const stateOptions = useMemo(() => [...new Set(projects.map((p) => p.state))].sort(), [projects])
  const typeOptions = useMemo(() => [...new Set(projects.map((p) => p.project_type))].sort(), [projects])

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

      {/* ---------- Phase 14: Historical Performance + Current Predicted Risk ---------- */}
      <AsyncSection
        status={overview.status}
        error={overview.error}
        data={overview.data}
        onRetry={overview.reload}
        loadingLabel="Loading portfolio risk overview…"
        errorTitle="Unable to load portfolio risk overview."
      >
        {(data) => (
          <>
            <div className="grid two-col-grid">
              <div className="card card-padded">
                <div className="card-header">
                  <h2>Historical Performance</h2>
                  <SourceLabel kind="historical" />
                </div>
                <p className="muted" style={{ fontSize: 11.5 }}>
                  Based on {formatNumber(data.historical.completed_project_count)} completed (terminal) projects.
                </p>
                <div className="grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
                  <div className="kpi-card">
                    <div className="kpi-label">Significant Delay Rate</div>
                    <div className="kpi-value" style={{ fontSize: 22 }}>{formatPercent(data.historical.significant_delay_rate * 100)}</div>
                    <div className="kpi-note">
                      {formatNumber(data.historical.significant_delay_count)} of {formatNumber(data.historical.completed_project_count)}
                    </div>
                  </div>
                  <div className="kpi-card">
                    <div className="kpi-label">Cost Overrun Rate</div>
                    <div className="kpi-value" style={{ fontSize: 22 }}>{formatPercent(data.historical.cost_overrun_rate * 100)}</div>
                    <div className="kpi-note">
                      {formatNumber(data.historical.cost_overrun_count)} of {formatNumber(data.historical.completed_project_count)}
                    </div>
                  </div>
                  <div className="kpi-card">
                    <div className="kpi-label">Mean Final Delay</div>
                    <div className="kpi-value" style={{ fontSize: 22 }}>{formatDays(data.historical.mean_final_delay_days)}</div>
                  </div>
                  <div className="kpi-card">
                    <div className="kpi-label">Mean Cost Overrun</div>
                    <div className="kpi-value" style={{ fontSize: 22 }}>{formatPercent(data.historical.mean_final_cost_overrun_pct)}</div>
                  </div>
                </div>
              </div>

              <div className="card card-padded">
                <div className="card-header">
                  <h2>Current Predicted Risk</h2>
                  <SourceLabel kind="predicted" />
                </div>
                {data.predicted.status === 'cache_unavailable' ? (
                  <DisclaimerBox warn>{data.predicted.message}</DisclaimerBox>
                ) : (
                  <>
                    <p className="muted" style={{ fontSize: 11.5 }}>
                      Based on {formatNumber(data.predicted.scored_project_count)} projects' latest non-terminal
                      snapshot. Computed at {formatDate(data.predicted.computed_at)}.
                    </p>
                    <div className="grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
                      <div className="kpi-card">
                        <div className="kpi-label">Avg. Delay Probability</div>
                        <div className="kpi-value" style={{ fontSize: 22 }}>
                          {formatPercent(data.predicted.avg_significant_delay_probability * 100)}
                        </div>
                      </div>
                      <div className="kpi-card">
                        <div className="kpi-label">Avg. Cost-Overrun Probability</div>
                        <div className="kpi-value" style={{ fontSize: 22 }}>
                          {formatPercent(data.predicted.avg_cost_overrun_probability * 100)}
                        </div>
                      </div>
                      <div className="kpi-card">
                        <div className="kpi-label">Avg. Predicted Delay</div>
                        <div className="kpi-value" style={{ fontSize: 22 }}>
                          {formatDays(data.predicted.avg_final_delay_days_predicted)}
                        </div>
                      </div>
                      <div className="kpi-card">
                        <div className="kpi-label">Avg. Predicted Cost Overrun</div>
                        <div className="kpi-value" style={{ fontSize: 22 }}>
                          {formatPercent(data.predicted.avg_final_cost_overrun_pct_predicted)}
                        </div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                      {RISK_LEVELS.map((lvl) => (
                        <RiskBadge key={lvl} level={lvl} label={`${lvl}: ${data.predicted.risk_level_counts[lvl] || 0}`} />
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="card card-padded">
              <div className="card-header">
                <h2>Risk Distribution</h2>
                <SourceLabel kind="predicted" />
              </div>
              {data.predicted.status === 'cache_unavailable' ? (
                <p className="muted">Unavailable until the prediction cache is generated.</p>
              ) : (
                <div className="grid two-col-grid">
                  {data.risk_distribution.map((td) => (
                    <div key={td.task_key}>
                      <h3 style={{ fontSize: 12.5, margin: '0 0 6px' }}>{TASK_LABELS[td.task_key]}</h3>
                      <HorizontalBarList data={td.buckets.map((b) => ({ name: b.label, value: b.count }))} color={PALETTE.navy} height={150} />
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="card card-padded">
              <div className="card-header">
                <h2>Executive Insights</h2>
              </div>
              <ul className="insight-list">
                {data.executive_insights.map((insight, i) => (
                  <li key={i}>{insight}</li>
                ))}
              </ul>
            </div>
          </>
        )}
      </AsyncSection>

      {/* ---------- Top Risk Projects ---------- */}
      <div className="card card-padded">
        <div className="card-header">
          <h2>Top Risk Projects</h2>
          <SourceLabel kind="predicted" />
        </div>
        <div className="filter-bar">
          <div className="field">
            <label htmlFor="risk-filter-state">State</label>
            <select
              id="risk-filter-state"
              className="select"
              value={riskFilters.state}
              onChange={(e) => setRiskFilters((f) => ({ ...f, state: e.target.value }))}
            >
              <option value="">All states</option>
              {stateOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="risk-filter-type">Project type</label>
            <select
              id="risk-filter-type"
              className="select"
              value={riskFilters.project_type}
              onChange={(e) => setRiskFilters((f) => ({ ...f, project_type: e.target.value }))}
            >
              <option value="">All types</option>
              {typeOptions.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="risk-filter-level">Risk level</label>
            <select
              id="risk-filter-level"
              className="select"
              value={riskFilters.risk_level}
              onChange={(e) => setRiskFilters((f) => ({ ...f, risk_level: e.target.value }))}
            >
              <option value="">All risk levels</option>
              {RISK_LEVELS.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>
        </div>
        <AsyncSection
          status={riskProjects.status}
          error={riskProjects.error}
          data={riskProjects.data}
          onRetry={riskProjects.reload}
          loadingLabel="Loading risk projects…"
          errorTitle="Unable to load risk projects."
          isEmpty={(d) => d.cache_status === 'cache_unavailable' || d.items.length === 0}
          emptyTitle={riskProjects.data?.cache_status === 'cache_unavailable' ? 'Prediction cache not generated yet.' : 'No projects match these filters.'}
          emptyMessage={riskProjects.data?.cache_message}
        >
          {(data) => (
            <>
              <TopRiskTable items={data.items} />
              <p className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>
                Showing {formatNumber(data.items.length)} of {formatNumber(data.total)} scored projects matching these filters.
              </p>
            </>
          )}
        </AsyncSection>
      </div>

      {/* ---------- Risk Matrix ---------- */}
      <div className="card card-padded">
        <div className="card-header">
          <h2>Risk Matrix (Delay Risk vs. Cost Risk)</h2>
          <SourceLabel kind="predicted" />
        </div>
        <AsyncSection
          status={riskMatrix.status}
          data={riskMatrix.data}
          loadingLabel="Loading risk matrix…"
          isEmpty={(d) => d.cache_status === 'cache_unavailable' || d.items.length === 0}
          emptyTitle="No data available for the risk matrix."
        >
          {(data) => (
            <>
              <RiskMatrixChart points={data.items} />
              <p className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>
                Showing {formatNumber(data.items.length)} of {formatNumber(data.total)} scored projects matching these filters.
              </p>
            </>
          )}
        </AsyncSection>
      </div>

      {/* ---------- State / Project-Type / Contractor Analytics ---------- */}
      <div className="card card-padded">
        <div className="card-header">
          <h2>Segment Analytics</h2>
        </div>
        <div className="dimension-tabs" style={{ marginBottom: 14 }}>
          {DIMENSIONS.map((d) => (
            <button
              key={d.key}
              type="button"
              className={`dimension-tab${segmentDimension === d.key ? ' active' : ''}`}
              onClick={() => setSegmentDimension(d.key)}
            >
              {d.label}
            </button>
          ))}
        </div>
        <AsyncSection
          status={segments.status}
          error={segments.error}
          data={segments.data}
          onRetry={segments.reload}
          loadingLabel="Loading segment analytics…"
          errorTitle="Unable to load segment analytics."
          isEmpty={(d) => d.entries.length === 0}
          emptyTitle="No segment data available."
        >
          {(data) => (
            <>
              <p className="muted" style={{ fontSize: 11.5 }}>
                Minimum sample threshold for comparative ranking on this dimension: n ≥ {data.min_sample_threshold}.
                Segments below this threshold are still shown, flagged "Small sample", never dropped.
              </p>
              <SegmentTable
                dimensionLabel={DIMENSIONS.find((d) => d.key === data.dimension)?.label || data.dimension}
                entries={data.entries}
                minSampleThreshold={data.min_sample_threshold}
              />
            </>
          )}
        </AsyncSection>
      </div>

      {/* ---------- Portfolio-Wide Model Drivers ---------- */}
      <div className="card card-padded">
        <div className="card-header">
          <h2>Portfolio-Wide Model Drivers</h2>
        </div>
        <AsyncSection
          status={drivers.status}
          error={drivers.error}
          data={drivers.data}
          onRetry={drivers.reload}
          loadingLabel="Loading model drivers…"
          errorTitle="Unable to load model drivers."
        >
          {(data) => (
            <>
              <p className="muted" style={{ fontSize: 11.5 }}>{data.methodology_note}</p>
              <div className="grid two-col-grid">
                {data.tasks.map((task) => {
                  const maxAbs = Math.max(...task.drivers.map((d) => Math.abs(d.mean_abs_shap)), 0.0001)
                  return (
                    <div key={task.task_key} className="card card-padded">
                      <div className="card-header">
                        <h3 style={{ margin: 0, fontSize: 13 }}>{task.label}</h3>
                        {!task.matches_serving_model && (
                          <span className="small-sample-tag" title="This global ranking explains a different model family than the one currently serving this task's predictions.">
                            Explains {task.model_family_explained}, not the serving model
                          </span>
                        )}
                      </div>
                      {task.drivers.slice(0, 8).map((d) => (
                        <DriverBar
                          key={d.raw_feature}
                          driver={{
                            feature: d.feature,
                            shap_value: d.mean_abs_shap,
                            direction: 'increases',
                            explanation: `Portfolio-wide mean |SHAP| = ${d.mean_abs_shap.toFixed(4)} (Phase 5 global ranking)`,
                          }}
                          maxAbs={maxAbs}
                        />
                      ))}
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </AsyncSection>
      </div>

      {/* ---------- Historical / Predicted Trends ---------- */}
      <div className="grid two-col-grid">
        <div className="card card-padded">
          <div className="card-header">
            <h2>Historical Trend</h2>
            <SourceLabel kind="historical" />
          </div>
          <p className="muted" style={{ fontSize: 11.5 }}>Grouped by each project's planned start-date cohort year.</p>
          <AsyncSection
            status={trends.status}
            error={trends.error}
            data={trends.data}
            onRetry={trends.reload}
            loadingLabel="Loading trends…"
            errorTitle="Unable to load trends."
          >
            {(data) => (
              <TrendLineChart
                data={data.historical}
                dataKey="significant_delay_rate"
                color={PALETTE.red}
                yFormatter={(v) => `${Math.round(v * 100)}%`}
              />
            )}
          </AsyncSection>
        </div>
        <div className="card card-padded">
          <div className="card-header">
            <h2>Predicted Trend</h2>
            <SourceLabel kind="predicted" />
          </div>
          <p className="muted" style={{ fontSize: 11.5 }}>Grouped by the reporting-month year of each project's latest non-terminal snapshot.</p>
          <AsyncSection
            status={trends.status}
            data={trends.data}
            loadingLabel="Loading trends…"
            isEmpty={(d) => d.predicted_status === 'cache_unavailable' || d.predicted.length === 0}
            emptyTitle="Predicted trend unavailable."
            emptyMessage={trends.data?.predicted_message}
          >
            {(data) => (
              <TrendLineChart data={data.predicted} dataKey="avg_composite_risk_score" color={PALETTE.blue} yFormatter={(v) => v.toFixed(0)} />
            )}
          </AsyncSection>
        </div>
      </div>

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
