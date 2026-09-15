import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { useProjectSnapshots } from '../hooks/useProjectSnapshots'
import { getDecisionIntelligence } from '../api/endpoints'
import { latestSnapshot } from '../utils/snapshots'
import AsyncSection, { EmptyState } from '../components/StateViews'
import ProjectPicker from '../components/ProjectPicker'
import MonthSelect from '../components/MonthSelect'
import DisclaimerBox from '../components/DisclaimerBox'
import DriverBar from '../components/DriverBar'
import EvidenceResultCard from '../components/EvidenceResultCard'
import InconsistencyCard from '../components/InconsistencyCard'
import { ProbabilityTile, RegressionTile } from '../components/PredictionTiles'
import PercentileGauge from '../components/DecisionIntelligence/PercentileGauge'
import PeerContextCard from '../components/DecisionIntelligence/PeerContextCard'
import DriverAlignmentRow from '../components/DecisionIntelligence/DriverAlignmentRow'
import { formatDays, formatPercent } from '../utils/format'
import { IconRisk, IconSimulator } from '../components/icons'

function ScenarioMetric({ label, before, after, unit }) {
  const delta = before != null && after != null ? after - before : null
  const trend = delta == null || Math.abs(delta) < 0.05 ? 'flat' : delta > 0 ? 'up' : 'down'
  const fmt = (v) => (v == null ? '—' : unit === 'pct' ? formatPercent(v) : formatDays(v))
  return (
    <div className="metric-row">
      <span>{label}</span>
      <span>
        {fmt(before)} → <strong>{fmt(after)}</strong>{' '}
        {delta != null && (
          <span className={`metric-delta ${trend}`}>
            ({delta > 0 ? '+' : ''}
            {unit === 'pct' ? delta.toFixed(1) : delta.toFixed(0)})
          </span>
        )}
      </span>
    </div>
  )
}

const PEER_DIMENSION_LABELS = { state: 'State Peers', project_type: 'Project-Type Peers', contractor: 'Contractor Peers' }

export default function DecisionIntelligence() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  if (!projectId) {
    return (
      <ProjectPicker
        title="Decision Intelligence"
        description="Select a project to see its risk prediction, live SHAP drivers, documentary evidence, and how it compares to the rest of the scored portfolio."
        basePath={(id) => `/projects/${id}/decision-intelligence`}
      />
    )
  }

  return <ProjectDecisionIntelligence projectId={projectId} searchParams={searchParams} setSearchParams={setSearchParams} navigate={navigate} />
}

function ProjectDecisionIntelligence({ projectId, searchParams, setSearchParams, navigate }) {
  const snapshots = useProjectSnapshots(projectId)
  const monthFromUrl = searchParams.get('month')
  const [selectedMonth, setSelectedMonth] = useState(monthFromUrl)

  useEffect(() => {
    if (!selectedMonth && snapshots.data && snapshots.data.length > 0) {
      setSelectedMonth(latestSnapshot(snapshots.data).reporting_month)
    }
  }, [snapshots.data, selectedMonth])

  function handleMonthChange(month) {
    setSelectedMonth(month)
    const next = new URLSearchParams(searchParams)
    next.set('month', month)
    setSearchParams(next, { replace: true })
  }

  const di = useApi(
    (signal) => getDecisionIntelligence(projectId, selectedMonth, signal),
    [projectId, selectedMonth],
    { skip: !selectedMonth }
  )

  if (snapshots.status === 'error' && snapshots.error?.status === 404) {
    return <EmptyState title={`Project "${projectId}" was not found.`} message="Check the project ID and try again." />
  }

  const maxAbs = (drivers) => Math.max(0.001, ...drivers.map((d) => Math.abs(d.shap_value)))

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Decision Intelligence</h1>
          <p>
            Project-level risk prediction combined with portfolio-wide context — percentile position, peer
            comparison, and live-vs-portfolio driver alignment — for <strong>{projectId}</strong>.
          </p>
        </div>
        <div className="page-header-actions">
          {snapshots.data && (
            <MonthSelect snapshots={snapshots.data} value={selectedMonth} onChange={handleMonthChange} id="decision-intelligence-month" />
          )}
          <button type="button" className="btn" onClick={() => navigate(`/projects/${projectId}/risk-summary?month=${selectedMonth || ''}`)}>
            <IconRisk size={15} /> Risk Summary
          </button>
          <button type="button" className="btn" onClick={() => navigate(`/projects/${projectId}/simulator?month=${selectedMonth || ''}`)}>
            <IconSimulator size={15} /> Open Simulator
          </button>
        </div>
      </div>

      <AsyncSection
        status={di.status}
        error={di.error}
        data={di.data}
        onRetry={di.reload}
        loadingLabel="Computing decision intelligence (prediction + SHAP + portfolio context)…"
        errorTitle="Unable to load decision intelligence for this project."
      >
        {(data) => (
          <>
            {/* 1. EXECUTIVE RISK */}
            <div className="card card-padded">
              <div className="card-header">
                <h2>
                  {data.project.project_name} ({data.project.project_id})
                </h2>
                <span className="badge badge-info">
                  {data.prediction_status === 'actual_outcome' ? 'Recorded final outcome' : 'Live model prediction'}
                </span>
              </div>
              <p className="muted" style={{ fontSize: 12.5 }}>
                {data.project.state} · {data.project.project_type} · reporting month {data.project.reporting_month} ·{' '}
                {data.project.months_since_start} months since start
              </p>

              <div className="grid kpi-grid">
                <ProbabilityTile
                  title="Significant Delay"
                  isActual={data.prediction_status === 'actual_outcome'}
                  probability={data.predictions.significant_delay.probability_of_significant_delay}
                  predictedClass={data.predictions.significant_delay.predicted_class}
                  actualValue={data.predictions.significant_delay.actual_value}
                  statusLabel={data.predictions.significant_delay.model_used ? `Model: ${data.predictions.significant_delay.model_used}` : 'Recorded outcome'}
                  summaryText={data.risk_summary.significant_delay_summary}
                />
                <RegressionTile
                  title="Predicted Delay Duration"
                  unit="days"
                  value={data.predictions.final_delay_days.predicted_final_delay_days ?? data.predictions.final_delay_days.actual_value}
                  statusLabel={data.predictions.final_delay_days.model_used ? `Model: ${data.predictions.final_delay_days.model_used}` : 'Recorded outcome'}
                  summaryText={data.risk_summary.final_delay_days_summary}
                />
                <ProbabilityTile
                  title="Cost Overrun"
                  isActual={data.prediction_status === 'actual_outcome'}
                  probability={data.predictions.cost_overrun.probability_of_cost_overrun}
                  predictedClass={data.predictions.cost_overrun.predicted_class}
                  actualValue={data.predictions.cost_overrun.actual_value}
                  statusLabel={data.predictions.cost_overrun.model_used ? `Model: ${data.predictions.cost_overrun.model_used}` : 'Recorded outcome'}
                  summaryText={data.risk_summary.cost_overrun_summary}
                />
                <RegressionTile
                  title="Predicted Cost Overrun %"
                  unit="pct"
                  value={
                    data.predictions.final_cost_overrun_pct.predicted_final_cost_overrun_pct ??
                    data.predictions.final_cost_overrun_pct.actual_value
                  }
                  statusLabel={data.predictions.final_cost_overrun_pct.model_used ? `Model: ${data.predictions.final_cost_overrun_pct.model_used}` : 'Recorded outcome'}
                  summaryText={data.risk_summary.final_cost_overrun_pct_summary}
                />
              </div>

              {data.risk_positioning.status === 'ok' ? (
                <PercentileGauge
                  percentile={data.risk_positioning.percentile}
                  riskLevel={data.risk_positioning.risk_level}
                  cohortSize={data.risk_positioning.cohort_size}
                />
              ) : (
                <DisclaimerBox warn>Portfolio-relative risk positioning unavailable — see "Portfolio Position" below.</DisclaimerBox>
              )}

              <div className="disclaimer-box" style={{ marginTop: 10 }}>
                Evidence strength: <strong>{data.evidence_strength}</strong> — {data.evidence_strength_basis}
              </div>
            </div>

            {/* 8. RECOMMENDED NEXT REVIEWS (shown early, mirrors RiskSummary's layout) */}
            {data.recommended_reviews.length > 0 && (
              <div className="card card-padded">
                <div className="card-header">
                  <h2>Recommended Reviews</h2>
                </div>
                <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {data.recommended_reviews.map((rec, i) => (
                    <li key={i} style={{ fontSize: 12.5 }}>
                      {rec.text}
                      <div className="muted" style={{ fontSize: 11 }}>
                        Basis: {rec.basis_type.replace(/_/g, ' ')} — {rec.basis_detail}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* 2. WHY THE MODEL CONSIDERS THIS PROJECT RISKY */}
            <div className="card card-padded">
              <div className="card-header">
                <h2>Live SHAP Risk Drivers</h2>
              </div>
              {data.risk_drivers.length === 0 ? (
                <DisclaimerBox warn>{data.shap_skipped_reason}</DisclaimerBox>
              ) : (
                <div className="grid two-col-grid">
                  {data.risk_drivers.map((task) => (
                    <div key={task.task_key} style={{ marginBottom: 14 }}>
                      <div className="section-title" style={{ fontSize: 13 }}>
                        {task.label}
                      </div>
                      <p className="muted" style={{ fontSize: 11, marginTop: -6 }}>
                        {task.model_used} · {task.explainer_type} · {task.shap_output_semantics}
                      </p>
                      {task.top_drivers.map((d) => (
                        <DriverBar key={d.rank} driver={d} maxAbs={maxAbs(task.top_drivers)} />
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 3. DOCUMENTARY EVIDENCE */}
            <div className="card card-padded">
              <div className="card-header">
                <h2>Supporting Evidence</h2>
              </div>
              <div className="stack">
                {data.documentary_evidence.map((item, i) => (
                  <div key={i}>
                    <div className="info-item-label">Query: “{item.query}”</div>
                    {item.not_found ? (
                      <EmptyState title="Not found in the available documents." />
                    ) : (
                      <>
                        <p className="evidence-text">{item.answer}</p>
                        <div className="stack" style={{ gap: 8 }}>
                          {item.results.map((r) => (
                            <EvidenceResultCard key={r.chunk_id} result={r} />
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* 4. CONTRADICTION / DATA QUALITY CONTEXT */}
            <div className="card card-padded">
              <div className="card-header">
                <h2>Potential Inconsistencies</h2>
              </div>
              {data.potential_inconsistencies.length === 0 ? (
                <EmptyState
                  title="No potential inconsistencies surfaced for this evidence."
                  message="This is not a claim that the underlying documents are free of inconsistencies — only that none were flagged for the evidence retrieved here."
                />
              ) : (
                <div className="stack" style={{ gap: 10 }}>
                  {data.potential_inconsistencies.map((flag) => (
                    <InconsistencyCard key={flag.flag_id} flag={flag} />
                  ))}
                </div>
              )}
            </div>

            {/* 5. PORTFOLIO POSITION */}
            <div className="card card-padded">
              <div className="card-header">
                <h2>Portfolio Position</h2>
              </div>
              {data.risk_positioning.status === 'ok' ? (
                <>
                  <PercentileGauge
                    percentile={data.risk_positioning.percentile}
                    riskLevel={data.risk_positioning.risk_level}
                    cohortSize={data.risk_positioning.cohort_size}
                  />
                  <p className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>
                    {data.risk_positioning.percentile_definition}
                  </p>
                </>
              ) : (
                <EmptyState
                  title={data.risk_positioning.status === 'cache_unavailable' ? 'Portfolio prediction cache unavailable.' : 'This project is not in the current portfolio prediction cache.'}
                  message={data.risk_positioning.message}
                />
              )}
              <DisclaimerBox>{data.risk_positioning.portfolio_relative_disclaimer}</DisclaimerBox>
              <DisclaimerBox>{data.risk_positioning.current_risk_basis_note}</DisclaimerBox>
            </div>

            {/* 6. PEER GROUP CONTEXT */}
            <div className="card card-padded">
              <div className="card-header">
                <h2>Peer Group Context</h2>
              </div>
              <div className="grid three-col-grid">
                {Object.entries(PEER_DIMENSION_LABELS).map(([dimension, label]) => (
                  <PeerContextCard key={dimension} label={label} entry={data.peer_context[dimension]} />
                ))}
              </div>
            </div>

            {/* 7. LIVE VS PORTFOLIO DRIVER ALIGNMENT */}
            <div className="card card-padded">
              <div className="card-header">
                <h2>Live vs. Portfolio Driver Alignment</h2>
              </div>
              <p className="muted" style={{ fontSize: 11.5, marginTop: -6 }}>
                Compares this project's own live SHAP top driver against the portfolio-wide top driver for the
                same task. Where the portfolio-wide ranking explains a different model family than the one
                actually serving that task's predictions, the comparison is marked not meaningful rather than
                shown as agree/disagree.
              </p>
              {data.driver_alignment.map((a) => (
                <DriverAlignmentRow key={a.task_key} alignment={a} />
              ))}
            </div>

            {/* 9. WHAT-IF SCENARIO */}
            <div className="card card-padded">
              <div className="card-header">
                <h2>Illustrative What-if Scenario</h2>
                <span className="badge badge-info">Illustrative, not a recommendation</span>
              </div>
              {data.scenario ? (
                <>
                  <p className="muted" style={{ fontSize: 12.5 }}>
                    {data.scenario.label} — <strong>{data.scenario.field}</strong> moved to its training-partition mean (
                    {data.scenario.reference_value}).
                  </p>
                  <div className="compare-col-label">Baseline → Simulated</div>
                  <ScenarioMetric
                    label="Delay probability"
                    unit="pct"
                    before={data.scenario.baseline.significant_delay.probability_of_significant_delay * 100}
                    after={data.scenario.simulated.significant_delay.probability_of_significant_delay * 100}
                  />
                  <ScenarioMetric
                    label="Delay days"
                    unit="days"
                    before={data.scenario.baseline.final_delay_days.predicted_final_delay_days}
                    after={data.scenario.simulated.final_delay_days.predicted_final_delay_days}
                  />
                  <ScenarioMetric
                    label="Cost overrun probability"
                    unit="pct"
                    before={data.scenario.baseline.cost_overrun.probability_of_cost_overrun * 100}
                    after={data.scenario.simulated.cost_overrun.probability_of_cost_overrun * 100}
                  />
                  <ScenarioMetric
                    label="Cost overrun %"
                    unit="pct"
                    before={data.scenario.baseline.final_cost_overrun_pct.predicted_final_cost_overrun_pct}
                    after={data.scenario.simulated.final_cost_overrun_pct.predicted_final_cost_overrun_pct}
                  />
                  <DisclaimerBox>{data.scenario.disclaimer}</DisclaimerBox>
                </>
              ) : (
                <DisclaimerBox warn>{data.scenario_skipped_reason}</DisclaimerBox>
              )}
            </div>

            <div className="card card-padded">
              <div className="card-header">
                <h2>Disclaimers</h2>
              </div>
              <div className="disclaimer-list">
                <DisclaimerBox>{data.disclaimers.system_identity}</DisclaimerBox>
                <DisclaimerBox>{data.disclaimers.ml_limitation}</DisclaimerBox>
                <DisclaimerBox>{data.disclaimers.causality_limitation}</DisclaimerBox>
                <DisclaimerBox>{data.disclaimers.scenario_limitation}</DisclaimerBox>
                <DisclaimerBox>{data.disclaimers.evidence_limitation}</DisclaimerBox>
                <DisclaimerBox>{data.disclaimers.inconsistency_limitation}</DisclaimerBox>
                <DisclaimerBox>{data.disclaimers.synthetic_data_disclaimer}</DisclaimerBox>
              </div>
            </div>
          </>
        )}
      </AsyncSection>
    </div>
  )
}
