import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { useProjectSnapshots } from '../hooks/useProjectSnapshots'
import { downloadReportPdf, getProject, getRiskSummary } from '../api/endpoints'
import { latestSnapshot } from '../utils/snapshots'
import AsyncSection, { EmptyState } from '../components/StateViews'
import ProjectPicker from '../components/ProjectPicker'
import MonthSelect from '../components/MonthSelect'
import DisclaimerBox from '../components/DisclaimerBox'
import RiskBadge from '../components/RiskBadge'
import { ProbabilityTile, RegressionTile } from '../components/PredictionTiles'
import { formatDate, formatMonthLabel, formatNumber } from '../utils/format'
import { IconDownload, IconPrint } from '../components/icons'

export default function Reports() {
  const { projectId } = useParams()
  if (!projectId) {
    return (
      <ProjectPicker
        title="Reports"
        description="Select a project to generate a print-friendly risk summary report."
        basePath={(id) => `/reports/${id}`}
      />
    )
  }
  return <ProjectReport projectId={projectId} />
}

function ProjectReport({ projectId }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const project = useApi((signal) => getProject(projectId, signal), [projectId])
  const snapshots = useProjectSnapshots(projectId)
  const [selectedMonth, setSelectedMonth] = useState(searchParams.get('month'))
  const [pdfState, setPdfState] = useState({ status: 'idle', error: null })

  useEffect(() => {
    if (!selectedMonth && snapshots.data && snapshots.data.length > 0) {
      setSelectedMonth(latestSnapshot(snapshots.data).reporting_month)
    }
  }, [snapshots.data, selectedMonth])

  function handleMonthChange(month) {
    setSelectedMonth(month)
    setPdfState({ status: 'idle', error: null })
    const next = new URLSearchParams(searchParams)
    next.set('month', month)
    setSearchParams(next, { replace: true })
  }

  const risk = useApi(
    (signal) => getRiskSummary(projectId, selectedMonth, signal),
    [projectId, selectedMonth],
    { skip: !selectedMonth }
  )

  async function handleDownloadPdf() {
    if (!selectedMonth || pdfState.status === 'loading') return
    setPdfState({ status: 'loading', error: null })
    try {
      const { blob, filename } = await downloadReportPdf(projectId, selectedMonth)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      setPdfState({ status: 'success', error: null })
    } catch (err) {
      setPdfState({ status: 'error', error: err })
    }
  }

  if (project.status === 'error' && project.error?.status === 404) {
    return <EmptyState title={`Project "${projectId}" was not found.`} message="Check the project ID and try again." />
  }

  return (
    <div className="stack">
      <div className="page-header no-print">
        <div>
          <h1>Report</h1>
          <p>A print-friendly risk summary report for a single project and reporting month, with a genuine backend-generated PDF download.</p>
        </div>
        <div className="page-header-actions">
          {snapshots.data && (
            <MonthSelect snapshots={snapshots.data} value={selectedMonth} onChange={handleMonthChange} id="report-month" />
          )}
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleDownloadPdf}
            disabled={!selectedMonth || pdfState.status === 'loading'}
          >
            <IconDownload size={15} /> {pdfState.status === 'loading' ? 'Generating PDF…' : 'Download PDF Report'}
          </button>
          <button type="button" className="btn" onClick={() => window.print()}>
            <IconPrint size={15} /> Print
          </button>
        </div>
      </div>

      {pdfState.status === 'error' && (
        <div className="no-print">
          <DisclaimerBox warn>
            Unable to generate the PDF report: {pdfState.error?.message || 'An unexpected error occurred.'}
          </DisclaimerBox>
        </div>
      )}

      <AsyncSection
        status={project.status}
        error={project.error}
        data={project.data}
        onRetry={project.reload}
        loadingLabel="Loading project…"
        errorTitle="Unable to load this project."
      >
        {(p) => (
          <AsyncSection
            status={risk.status}
            error={risk.error}
            data={risk.data}
            onRetry={risk.reload}
            loadingLabel="Building report…"
            errorTitle="Unable to build the report."
          >
            {(data) => (
              <div className="card card-padded" id="report-content">
                <div style={{ borderBottom: '2px solid var(--navy-900)', paddingBottom: 14, marginBottom: 14 }}>
                  <h1 style={{ margin: 0, fontSize: 19 }}>
                    HRI Risk Summary Report — {p.project_id}
                  </h1>
                  <p className="muted" style={{ fontSize: 12 }}>
                    {p.project_name} · {p.state} · {p.project_type} · Reporting month {formatMonthLabel(data.project.reporting_month)}
                  </p>
                  <p className="muted" style={{ fontSize: 11 }}>
                    Generated {new Date().toLocaleString('en-IN')} · Prototype decision-support system, not an official NHAI report.
                  </p>
                </div>

                <div className="info-grid" style={{ marginBottom: 18 }}>
                  <div>
                    <div className="info-item-label">Highway Number</div>
                    <div className="info-item-value">{p.highway_number}</div>
                  </div>
                  <div>
                    <div className="info-item-label">Contractor</div>
                    <div className="info-item-value">{p.contractor || '—'}</div>
                  </div>
                  <div>
                    <div className="info-item-label">Length</div>
                    <div className="info-item-value">{formatNumber(p.project_length_km, 1)} km</div>
                  </div>
                  <div>
                    <div className="info-item-label">Planned Start</div>
                    <div className="info-item-value">{formatDate(p.planned_start_date)}</div>
                  </div>
                  <div>
                    <div className="info-item-label">Planned Completion</div>
                    <div className="info-item-value">{formatDate(p.planned_completion_date)}</div>
                  </div>
                  <div>
                    <div className="info-item-label">Status</div>
                    <div className="info-item-value">
                      <RiskBadge level={p.current_status === 'Completed' ? 'low' : 'medium'} label={p.current_status} />
                    </div>
                  </div>
                </div>

                <h2 className="section-title">Risk Overview</h2>
                <div className="grid kpi-grid" style={{ marginBottom: 18 }}>
                  <ProbabilityTile
                    title="Significant Delay"
                    isActual={data.prediction_status === 'actual_outcome'}
                    probability={data.predictions.significant_delay.probability_of_significant_delay}
                    predictedClass={data.predictions.significant_delay.predicted_class}
                    actualValue={data.predictions.significant_delay.actual_value}
                    summaryText={data.risk_summary.significant_delay_summary}
                  />
                  <RegressionTile
                    title="Delay Duration"
                    unit="days"
                    value={data.predictions.final_delay_days.predicted_final_delay_days ?? data.predictions.final_delay_days.actual_value}
                    summaryText={data.risk_summary.final_delay_days_summary}
                  />
                  <ProbabilityTile
                    title="Cost Overrun"
                    isActual={data.prediction_status === 'actual_outcome'}
                    probability={data.predictions.cost_overrun.probability_of_cost_overrun}
                    predictedClass={data.predictions.cost_overrun.predicted_class}
                    actualValue={data.predictions.cost_overrun.actual_value}
                    summaryText={data.risk_summary.cost_overrun_summary}
                  />
                  <RegressionTile
                    title="Cost Overrun %"
                    unit="pct"
                    value={
                      data.predictions.final_cost_overrun_pct.predicted_final_cost_overrun_pct ??
                      data.predictions.final_cost_overrun_pct.actual_value
                    }
                    summaryText={data.risk_summary.final_cost_overrun_pct_summary}
                  />
                </div>

                <h2 className="section-title">Evidence &amp; Verification</h2>
                <p style={{ fontSize: 12.5 }}>
                  Evidence strength: <strong>{data.evidence_strength}</strong> — {data.evidence_strength_basis}
                </p>
                <p style={{ fontSize: 12.5 }}>
                  Potential inconsistencies flagged for this evidence: <strong>{data.potential_inconsistencies.length}</strong>{' '}
                  (each requires human verification; none are confirmed errors).
                </p>

                {data.recommended_reviews.length > 0 && (
                  <>
                    <h2 className="section-title">Recommended Reviews</h2>
                    <ul style={{ fontSize: 12.5, paddingLeft: 18 }}>
                      {data.recommended_reviews.map((rec, i) => (
                        <li key={i}>{rec.text}</li>
                      ))}
                    </ul>
                  </>
                )}

                <h2 className="section-title">Disclaimers</h2>
                <div className="disclaimer-list">
                  <DisclaimerBox>{data.disclaimers.system_identity}</DisclaimerBox>
                  <DisclaimerBox>{data.disclaimers.ml_limitation}</DisclaimerBox>
                  <DisclaimerBox>{data.disclaimers.synthetic_data_disclaimer}</DisclaimerBox>
                </div>
              </div>
            )}
          </AsyncSection>
        )}
      </AsyncSection>
    </div>
  )
}
