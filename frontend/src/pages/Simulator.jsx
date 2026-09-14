import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { useProjectSnapshots } from '../hooks/useProjectSnapshots'
import { getProjectSnapshot, runSimulation } from '../api/endpoints'
import { ApiError } from '../api/client'
import { latestNonTerminalSnapshot, latestSnapshot } from '../utils/snapshots'
import { SIMULATOR_FIELDS } from '../utils/simulatorFields'
import AsyncSection, { EmptyState, ErrorState } from '../components/StateViews'
import ProjectPicker from '../components/ProjectPicker'
import MonthSelect from '../components/MonthSelect'
import DisclaimerBox from '../components/DisclaimerBox'
import { ProbabilityTile, RegressionTile } from '../components/PredictionTiles'

export default function Simulator() {
  const { projectId } = useParams()
  if (!projectId) {
    return (
      <ProjectPicker
        title="What-if Simulator"
        description="Select a project to re-score its prediction under a hypothetical assumption."
        basePath={(id) => `/projects/${id}/simulator`}
      />
    )
  }
  return <ProjectSimulator projectId={projectId} />
}

function ProjectSimulator({ projectId }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const snapshots = useProjectSnapshots(projectId)
  const [selectedMonth, setSelectedMonth] = useState(searchParams.get('month'))
  const [overrides, setOverrides] = useState({})
  const [result, setResult] = useState({ status: 'idle', data: null, error: null })

  useEffect(() => {
    if (!selectedMonth && snapshots.data && snapshots.data.length > 0) {
      const preferred = latestNonTerminalSnapshot(snapshots.data) || latestSnapshot(snapshots.data)
      setSelectedMonth(preferred.reporting_month)
    }
  }, [snapshots.data, selectedMonth])

  const baseline = useApi(
    (signal) => getProjectSnapshot(projectId, selectedMonth, signal),
    [projectId, selectedMonth],
    { skip: !selectedMonth }
  )

  function handleMonthChange(month) {
    setSelectedMonth(month)
    setOverrides({})
    setResult({ status: 'idle', data: null, error: null })
    const next = new URLSearchParams(searchParams)
    next.set('month', month)
    setSearchParams(next, { replace: true })
  }

  function handleFieldChange(field, rawValue) {
    setOverrides((prev) => {
      const next = { ...prev }
      if (rawValue === '') {
        delete next[field]
      } else {
        next[field] = Number(rawValue)
      }
      return next
    })
  }

  function handleReset() {
    setOverrides({})
    setResult({ status: 'idle', data: null, error: null })
  }

  async function handleRunSimulation() {
    setResult({ status: 'loading', data: null, error: null })
    try {
      const data = await runSimulation(projectId, selectedMonth, overrides)
      setResult({ status: 'success', data, error: null })
    } catch (err) {
      setResult({ status: 'error', data: null, error: err })
    }
  }

  if (snapshots.status === 'error' && snapshots.error?.status === 404) {
    return <EmptyState title={`Project "${projectId}" was not found.`} message="Check the project ID and try again." />
  }

  const isTerminal = baseline.data?.is_terminal_snapshot

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>What-if Simulator</h1>
          <p>
            Re-score <strong>{projectId}</strong>'s prediction under hypothetical absolute overrides. This is model
            re-scoring, not a forecast of what will actually happen.
          </p>
        </div>
        <div className="page-header-actions">
          {snapshots.data && (
            <MonthSelect snapshots={snapshots.data} value={selectedMonth} onChange={handleMonthChange} id="simulator-month" />
          )}
        </div>
      </div>

      <AsyncSection
        status={baseline.status}
        error={baseline.error}
        data={baseline.data}
        onRetry={baseline.reload}
        loadingLabel="Loading project snapshot…"
        errorTitle="Unable to load this snapshot."
      >
        {(snapshot) =>
          isTerminal ? (
            <DisclaimerBox warn>
              Simulation is unavailable for this snapshot: it is terminal (
              <code>is_terminal_snapshot=true</code>) and already records the project's known final outcome, so a
              hypothetical override cannot be isolated from that known result. Select an earlier, non-terminal
              reporting month above.
            </DisclaimerBox>
          ) : (
            <>
              <div className="card card-padded">
                <div className="card-header">
                  <h2>Scenario Inputs</h2>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button type="button" className="btn btn-sm" onClick={handleReset} disabled={Object.keys(overrides).length === 0}>
                      Reset
                    </button>
                    <button type="button" className="btn btn-primary btn-sm" onClick={handleRunSimulation}>
                      Run Simulation
                    </button>
                  </div>
                </div>
                <p className="muted" style={{ fontSize: 12, marginTop: -6 }}>
                  Fields left unchanged keep this snapshot's recorded value. Only edited fields are sent as overrides.
                </p>
                <div className="grid three-col-grid">
                  {SIMULATOR_FIELDS.map((f) => {
                    const baselineValue = snapshot[f.key]
                    const value = overrides[f.key] ?? baselineValue ?? ''
                    return (
                      <div className="field" key={f.key}>
                        <label htmlFor={`sim-${f.key}`}>{f.label}</label>
                        <input
                          id={`sim-${f.key}`}
                          className="input"
                          type="number"
                          min={f.min}
                          max={f.max}
                          step={f.step}
                          value={value}
                          placeholder={baselineValue == null ? 'not recorded' : undefined}
                          onChange={(e) => handleFieldChange(f.key, e.target.value)}
                        />
                        {f.key in overrides && baselineValue != null && (
                          <span className="muted" style={{ fontSize: 11 }}>baseline: {baselineValue}</span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

              {result.status === 'loading' && <div className="card card-padded"><AsyncSection status="loading" loadingLabel="Re-scoring baseline and simulated scenarios…" /></div>}

              {result.status === 'error' && (
                <div className="card card-padded">
                  <ErrorState
                    title="Simulation request failed."
                    message={
                      result.error instanceof ApiError
                        ? result.error.message
                        : 'Unexpected error running the simulation.'
                    }
                    onRetry={handleRunSimulation}
                  />
                </div>
              )}

              {result.status === 'success' && (
                <SimulationResult data={result.data} />
              )}
            </>
          )
        }
      </AsyncSection>
    </div>
  )
}

function SimulationResult({ data }) {
  return (
    <>
      {data.overrides.length > 0 && (
        <div className="card card-padded">
          <div className="card-header">
            <h2>Applied Overrides</h2>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Original</th>
                  <th>Simulated</th>
                  <th>Delta</th>
                </tr>
              </thead>
              <tbody>
                {data.overrides.map((o) => (
                  <tr key={o.field}>
                    <td>{o.field}</td>
                    <td>{o.original_value ?? 'not recorded'}</td>
                    <td>{o.simulated_value}</td>
                    <td>{o.delta == null ? '—' : o.delta.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {data.extrapolation_warnings.length > 0 && (
        <div className="card card-padded">
          <div className="card-header">
            <h2>Training-Range Warnings</h2>
          </div>
          <div className="disclaimer-list">
            {data.extrapolation_warnings.map((w) => (
              <DisclaimerBox warn key={w.field}>
                {w.message} (training range {w.training_min}–{w.training_max}, simulated {w.simulated_value})
              </DisclaimerBox>
            ))}
          </div>
        </div>
      )}

      <div className="card card-padded">
        <div className="card-header">
          <h2>Baseline vs Simulated</h2>
        </div>
        <div className="stack">
          <div>
            <div className="compare-col-label">Baseline</div>
            <div className="grid kpi-grid">
              <ProbabilityTile
                title="Significant Delay"
                probability={data.baseline_predictions.significant_delay.probability_of_significant_delay}
                predictedClass={data.baseline_predictions.significant_delay.predicted_class}
              />
              <RegressionTile
                title="Delay Duration"
                unit="days"
                value={data.baseline_predictions.final_delay_days.predicted_final_delay_days}
              />
              <ProbabilityTile
                title="Cost Overrun"
                probability={data.baseline_predictions.cost_overrun.probability_of_cost_overrun}
                predictedClass={data.baseline_predictions.cost_overrun.predicted_class}
              />
              <RegressionTile
                title="Cost Overrun %"
                unit="pct"
                value={data.baseline_predictions.final_cost_overrun_pct.predicted_final_cost_overrun_pct}
              />
            </div>
          </div>
          <div>
            <div className="compare-col-label">Simulated</div>
            <div className="grid kpi-grid">
              <ProbabilityTile
                title="Significant Delay"
                probability={data.simulated_predictions.significant_delay.probability_of_significant_delay}
                predictedClass={data.simulated_predictions.significant_delay.predicted_class}
              />
              <RegressionTile
                title="Delay Duration"
                unit="days"
                value={data.simulated_predictions.final_delay_days.predicted_final_delay_days}
              />
              <ProbabilityTile
                title="Cost Overrun"
                probability={data.simulated_predictions.cost_overrun.probability_of_cost_overrun}
                predictedClass={data.simulated_predictions.cost_overrun.predicted_class}
              />
              <RegressionTile
                title="Cost Overrun %"
                unit="pct"
                value={data.simulated_predictions.final_cost_overrun_pct.predicted_final_cost_overrun_pct}
              />
            </div>
          </div>
        </div>
      </div>

      <DisclaimerBox>{data.simulation_disclaimer}</DisclaimerBox>
      <DisclaimerBox>{data.synthetic_data_disclaimer}</DisclaimerBox>
    </>
  )
}
