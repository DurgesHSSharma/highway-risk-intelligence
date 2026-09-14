import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { useProjectSnapshots } from '../hooks/useProjectSnapshots'
import { getProject } from '../api/endpoints'
import { findSnapshot, latestSnapshot } from '../utils/snapshots'
import AsyncSection, { EmptyState } from '../components/StateViews'
import RiskBadge from '../components/RiskBadge'
import MonthSelect from '../components/MonthSelect'
import ProgressBar from '../components/ProgressBar'
import { formatCrore, formatDate, formatDays, formatNumber, formatPercent, titleCase } from '../utils/format'
import { IconRisk, IconSimulator } from '../components/icons'

const DELAY_FACTORS = [
  ['land_acquisition_delay_days', 'Land Acquisition'],
  ['utility_shifting_delay_days', 'Utility Shifting'],
  ['environment_clearance_delay_days', 'Environment Clearance'],
  ['material_delay_days', 'Material'],
  ['labour_shortage_days', 'Labour Shortage'],
  ['equipment_unavailability_days', 'Equipment Unavailability'],
  ['weather_disruption_days', 'Weather Disruption'],
  ['traffic_diversion_delay_days', 'Traffic Diversion'],
  ['design_change_delay_days', 'Design Changes'],
  ['approval_delay_days', 'Approvals'],
]

export default function ProjectDetails() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const project = useApi((signal) => getProject(projectId, signal), [projectId])
  const snapshots = useProjectSnapshots(projectId)
  const [selectedMonth, setSelectedMonth] = useState(null)

  useEffect(() => {
    if (snapshots.data && snapshots.data.length > 0 && !selectedMonth) {
      setSelectedMonth(latestSnapshot(snapshots.data).reporting_month)
    }
  }, [snapshots.data, selectedMonth])

  if (project.status === 'error' && project.error?.status === 404) {
    return (
      <EmptyState
        title={`Project "${projectId}" was not found.`}
        message="Check the project ID, or browse the projects list."
        icon={<IconRisk size={26} />}
      />
    )
  }

  return (
    <div className="stack">
      <AsyncSection
        status={project.status}
        error={project.error}
        data={project.data}
        onRetry={project.reload}
        loadingLabel="Loading project…"
        errorTitle="Unable to load this project."
      >
        {(p) => (
          <div className="page-header">
            <div>
              <h1>
                {p.project_id} — {p.project_name}
              </h1>
              <p>
                {p.highway_number} · {p.state} · {p.project_type} · {formatNumber(p.project_length_km, 1)} km
              </p>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <RiskBadge level={p.current_status === 'Completed' ? 'low' : 'medium'} label={p.current_status} />
                <span className="badge badge-neutral">{p.data_provenance}</span>
              </div>
            </div>
            <div className="page-header-actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate(`/projects/${projectId}/risk-summary${selectedMonth ? `?month=${selectedMonth}` : ''}`)}
              >
                <IconRisk size={15} /> AI Risk Summary
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => navigate(`/projects/${projectId}/simulator${selectedMonth ? `?month=${selectedMonth}` : ''}`)}
              >
                <IconSimulator size={15} /> What-if Simulator
              </button>
            </div>
          </div>
        )}
      </AsyncSection>

      {project.status === 'success' && (
        <>
          <div className="card card-padded">
            <div className="card-header">
              <h2>Project Information</h2>
            </div>
            <div className="info-grid">
              <div>
                <div className="info-item-label">Contractor</div>
                <div className="info-item-value">{project.data.contractor || '—'}</div>
              </div>
              <div>
                <div className="info-item-label">Contract Value</div>
                <div className="info-item-value">{formatCrore(project.data.original_contract_value_inr_cr)}</div>
              </div>
              <div>
                <div className="info-item-label">Planned Duration</div>
                <div className="info-item-value">{project.data.planned_duration_months} months</div>
              </div>
              <div>
                <div className="info-item-label">Planned Start</div>
                <div className="info-item-value">{formatDate(project.data.planned_start_date)}</div>
              </div>
              <div>
                <div className="info-item-label">Planned Completion</div>
                <div className="info-item-value">{formatDate(project.data.planned_completion_date)}</div>
              </div>
              <div>
                <div className="info-item-label">Data Source</div>
                <div className="info-item-value">{project.data.data_provenance}</div>
              </div>
            </div>
          </div>

          <AsyncSection
            status={snapshots.status}
            error={snapshots.error}
            data={snapshots.data}
            onRetry={snapshots.reload}
            loadingLabel="Loading monthly snapshots…"
            errorTitle="Unable to load monthly snapshots."
            isEmpty={(d) => d.length === 0}
            emptyTitle="No monthly snapshots recorded for this project."
          >
            {(snapshotList) => {
              const snapshot = findSnapshot(snapshotList, selectedMonth) || latestSnapshot(snapshotList)
              if (!snapshot) return null
              return (
                <>
                  <div className="card card-padded">
                    <div className="card-header">
                      <h2>Monthly Snapshot</h2>
                      <MonthSelect snapshots={snapshotList} value={selectedMonth} onChange={setSelectedMonth} />
                    </div>
                    {snapshot.is_terminal_snapshot && (
                      <div className="disclaimer-box" style={{ marginBottom: 14 }}>
                        This is the project's terminal snapshot — it records the known final outcome rather than
                        an in-progress state.
                      </div>
                    )}
                    <div className="grid three-col-grid">
                      <div>
                        <div className="info-item-label">Months Since Start</div>
                        <div className="info-item-value">{snapshot.months_since_start}</div>
                      </div>
                      <div>
                        <div className="info-item-label">Snapshot Status</div>
                        <div className="info-item-value">{titleCase(snapshot.project_status)}</div>
                      </div>
                      <div>
                        <div className="info-item-label">Contractor Productivity Factor</div>
                        <div className="info-item-value">{formatNumber(snapshot.contractor_productivity_factor, 2)}</div>
                      </div>
                    </div>
                  </div>

                  <div className="grid two-col-grid">
                    <div className="card card-padded">
                      <div className="card-header">
                        <h2>Progress</h2>
                      </div>
                      <ProgressBar
                        label="Physical progress"
                        value={snapshot.actual_physical_progress_pct}
                        planned={snapshot.planned_physical_progress_pct}
                      />
                      <ProgressBar
                        label="Financial progress"
                        value={snapshot.actual_financial_progress_pct}
                        planned={snapshot.planned_financial_progress_pct}
                      />
                      <p className="muted" style={{ fontSize: 11.5, marginTop: 10, marginBottom: 0 }}>
                        Physical variance {formatPercent(snapshot.physical_progress_variance_pct)} · Financial variance{' '}
                        {snapshot.financial_progress_variance_pct == null
                          ? 'not recorded'
                          : formatPercent(snapshot.financial_progress_variance_pct)}
                      </p>
                    </div>

                    <div className="card card-padded">
                      <div className="card-header">
                        <h2>Cost Tracking</h2>
                      </div>
                      <div className="metric-row">
                        <span>Planned cost to date</span>
                        <strong>{formatCrore(snapshot.planned_cost_to_date_inr_cr)}</strong>
                      </div>
                      <div className="metric-row">
                        <span>Actual cost to date</span>
                        <strong>{formatCrore(snapshot.actual_cost_to_date_inr_cr)}</strong>
                      </div>
                      <div className="metric-row">
                        <span>Actual expenditure (month)</span>
                        <strong>
                          {snapshot.actual_expenditure_inr_cr == null ? 'not recorded' : formatCrore(snapshot.actual_expenditure_inr_cr)}
                        </strong>
                      </div>
                      <div className="metric-row">
                        <span>Material / Labour / Equipment</span>
                        <strong>
                          {formatCrore(snapshot.material_cost_inr_cr, 0)} / {formatCrore(snapshot.labour_cost_inr_cr, 0)} /{' '}
                          {formatCrore(snapshot.equipment_cost_inr_cr, 0)}
                        </strong>
                      </div>
                      <div className="metric-row">
                        <span>Delay-related cost</span>
                        <strong>{formatCrore(snapshot.delay_related_cost_inr_cr)}</strong>
                      </div>
                    </div>
                  </div>

                  <div className="card card-padded">
                    <div className="card-header">
                      <h2>Delay Factors (cumulative days)</h2>
                    </div>
                    <div className="grid three-col-grid">
                      {DELAY_FACTORS.map(([key, label]) => (
                        <div key={key} className="metric-row">
                          <span>{label}</span>
                          <strong>{snapshot[key] == null ? 'not recorded' : formatDays(snapshot[key])}</strong>
                        </div>
                      ))}
                    </div>
                  </div>

                  {snapshot.is_terminal_snapshot && (
                    <div className="card card-padded">
                      <div className="card-header">
                        <h2>Recorded Final Outcome</h2>
                      </div>
                      <div className="grid three-col-grid">
                        <div>
                          <div className="info-item-label">Significant Delay</div>
                          <div className="info-item-value">
                            <RiskBadge level={snapshot.significant_delay ? 'high' : 'low'} label={snapshot.significant_delay ? 'Yes' : 'No'} />
                          </div>
                        </div>
                        <div>
                          <div className="info-item-label">Final Delay</div>
                          <div className="info-item-value">{formatDays(snapshot.final_delay_days)}</div>
                        </div>
                        <div>
                          <div className="info-item-label">Cost Overrun</div>
                          <div className="info-item-value">
                            <RiskBadge level={snapshot.cost_overrun ? 'high' : 'low'} label={snapshot.cost_overrun ? 'Yes' : 'No'} />
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )
            }}
          </AsyncSection>
        </>
      )}
    </div>
  )
}
