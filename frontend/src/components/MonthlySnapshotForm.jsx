import { useState } from 'react'
import { addProjectSnapshot } from '../api/endpoints'
import { ApiError } from '../api/client'
import { ErrorState } from './StateViews'
import DisclaimerBox from './DisclaimerBox'

// Phase 17B monthly progress update form: POST /projects/{id}/snapshots.
// Field set mirrors backend/app/schemas/project_lifecycle.py::SnapshotCreate
// exactly. Actual-outcome fields only appear (and are required) once the
// caller picks project_status="Completed" -- an ordinary "Ongoing" update
// never sends them, matching the backend's own rejection of that combination.
const DELAY_FACTOR_FIELDS = [
  ['land_acquisition_delay_days', 'Land Acquisition (days)'],
  ['utility_shifting_delay_days', 'Utility Shifting (days)'],
  ['environment_clearance_delay_days', 'Environment Clearance (days)'],
  ['material_delay_days', 'Material (days)'],
  ['labour_shortage_days', 'Labour Shortage (days)'],
  ['equipment_unavailability_days', 'Equipment Unavailability (days)'],
  ['weather_disruption_days', 'Weather Disruption (days)'],
  ['traffic_diversion_delay_days', 'Traffic Diversion (days)'],
  ['design_change_delay_days', 'Design Changes (days)'],
  ['approval_delay_days', 'Approvals (days)'],
]

const EMPTY_FORM = {
  reporting_month: '',
  project_status: 'Ongoing',
  planned_physical_progress_pct: '',
  actual_physical_progress_pct: '',
  planned_financial_progress_pct: '',
  actual_financial_progress_pct: '',
  planned_cost_to_date_inr_cr: '',
  actual_expenditure_inr_cr: '',
  actual_cost_to_date_inr_cr: '',
  material_cost_inr_cr: '',
  labour_cost_inr_cr: '',
  equipment_cost_inr_cr: '',
  variation_cost_inr_cr: '',
  delay_related_cost_inr_cr: '',
  contractor_productivity_factor: '1.0',
  land_acquisition_delay_days: '0',
  utility_shifting_delay_days: '0',
  environment_clearance_delay_days: '0',
  material_delay_days: '0',
  labour_shortage_days: '0',
  equipment_unavailability_days: '0',
  weather_disruption_days: '0',
  traffic_diversion_delay_days: '0',
  design_change_delay_days: '0',
  approval_delay_days: '0',
  final_delay_days: '',
  significant_delay: '',
  final_cost_overrun_pct: '',
  cost_overrun: '',
}

export default function MonthlySnapshotForm({ projectId, onSuccess, onCancel }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [submitState, setSubmitState] = useState({ status: 'idle', error: null })

  function set(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  function buildPayload() {
    const num = (v) => (v === '' ? undefined : Number(v))
    const numOrNull = (v) => (v === '' ? null : Number(v))
    const payload = {
      reporting_month: form.reporting_month,
      project_status: form.project_status,
      planned_physical_progress_pct: num(form.planned_physical_progress_pct),
      actual_physical_progress_pct: num(form.actual_physical_progress_pct),
      planned_financial_progress_pct: num(form.planned_financial_progress_pct),
      actual_financial_progress_pct: numOrNull(form.actual_financial_progress_pct),
      planned_cost_to_date_inr_cr: num(form.planned_cost_to_date_inr_cr),
      actual_expenditure_inr_cr: numOrNull(form.actual_expenditure_inr_cr),
      actual_cost_to_date_inr_cr: num(form.actual_cost_to_date_inr_cr),
      material_cost_inr_cr: num(form.material_cost_inr_cr),
      labour_cost_inr_cr: num(form.labour_cost_inr_cr),
      equipment_cost_inr_cr: num(form.equipment_cost_inr_cr),
      variation_cost_inr_cr: numOrNull(form.variation_cost_inr_cr),
      delay_related_cost_inr_cr: num(form.delay_related_cost_inr_cr),
      contractor_productivity_factor: num(form.contractor_productivity_factor),
    }
    for (const [key] of DELAY_FACTOR_FIELDS) {
      payload[key] = num(form[key])
    }
    if (form.project_status === 'Completed') {
      payload.final_delay_days = num(form.final_delay_days)
      payload.significant_delay = form.significant_delay === '' ? undefined : Number(form.significant_delay)
      payload.final_cost_overrun_pct = num(form.final_cost_overrun_pct)
      payload.cost_overrun = form.cost_overrun === '' ? undefined : Number(form.cost_overrun)
    }
    return payload
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitState({ status: 'loading', error: null })
    try {
      await addProjectSnapshot(projectId, buildPayload())
      setSubmitState({ status: 'idle', error: null })
      onSuccess?.()
    } catch (err) {
      setSubmitState({ status: 'error', error: err })
    }
  }

  const isCompleting = form.project_status === 'Completed'

  return (
    <form className="card card-padded" onSubmit={handleSubmit}>
      <div className="card-header">
        <h2>Add Monthly Update</h2>
        {onCancel && (
          <button type="button" className="btn btn-sm" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>

      <div className="grid three-col-grid">
        <div className="field">
          <label htmlFor="ms-month">Reporting Month</label>
          <input
            id="ms-month"
            className="input"
            type="month"
            required
            value={form.reporting_month}
            onChange={(e) => set('reporting_month', e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="ms-status">Status This Month</label>
          <select id="ms-status" className="select" value={form.project_status} onChange={(e) => set('project_status', e.target.value)}>
            <option value="Ongoing">Ongoing</option>
            <option value="Completed">Completed (terminal — records the final actual outcome)</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="ms-cpf">Contractor Productivity Factor</label>
          <input
            id="ms-cpf"
            className="input"
            type="number"
            step="0.01"
            required
            value={form.contractor_productivity_factor}
            onChange={(e) => set('contractor_productivity_factor', e.target.value)}
          />
        </div>
      </div>

      <div className="card-header" style={{ marginTop: 10 }}>
        <h3 style={{ margin: 0, fontSize: 13 }}>Progress</h3>
      </div>
      <div className="grid three-col-grid">
        <NumField id="ms-ppp" label="Planned Physical Progress (%)" value={form.planned_physical_progress_pct} onChange={(v) => set('planned_physical_progress_pct', v)} required />
        <NumField id="ms-app" label="Actual Physical Progress (%)" value={form.actual_physical_progress_pct} onChange={(v) => set('actual_physical_progress_pct', v)} required />
        <NumField id="ms-pfp" label="Planned Financial Progress (%)" value={form.planned_financial_progress_pct} onChange={(v) => set('planned_financial_progress_pct', v)} required />
        <NumField id="ms-afp" label="Actual Financial Progress (%, optional)" value={form.actual_financial_progress_pct} onChange={(v) => set('actual_financial_progress_pct', v)} />
      </div>

      <div className="card-header" style={{ marginTop: 10 }}>
        <h3 style={{ margin: 0, fontSize: 13 }}>Cost Tracking (INR Cr)</h3>
      </div>
      <div className="grid three-col-grid">
        <NumField id="ms-pctd" label="Planned Cost to Date" value={form.planned_cost_to_date_inr_cr} onChange={(v) => set('planned_cost_to_date_inr_cr', v)} required />
        <NumField id="ms-actd" label="Actual Cost to Date" value={form.actual_cost_to_date_inr_cr} onChange={(v) => set('actual_cost_to_date_inr_cr', v)} required />
        <NumField id="ms-aexp" label="Actual Expenditure This Month (optional)" value={form.actual_expenditure_inr_cr} onChange={(v) => set('actual_expenditure_inr_cr', v)} />
        <NumField id="ms-mat" label="Material Cost" value={form.material_cost_inr_cr} onChange={(v) => set('material_cost_inr_cr', v)} required />
        <NumField id="ms-lab" label="Labour Cost" value={form.labour_cost_inr_cr} onChange={(v) => set('labour_cost_inr_cr', v)} required />
        <NumField id="ms-equip" label="Equipment Cost" value={form.equipment_cost_inr_cr} onChange={(v) => set('equipment_cost_inr_cr', v)} required />
        <NumField id="ms-var" label="Variation Cost (optional)" value={form.variation_cost_inr_cr} onChange={(v) => set('variation_cost_inr_cr', v)} />
        <NumField id="ms-delaycost" label="Delay-Related Cost" value={form.delay_related_cost_inr_cr} onChange={(v) => set('delay_related_cost_inr_cr', v)} required />
      </div>

      <div className="card-header" style={{ marginTop: 10 }}>
        <h3 style={{ margin: 0, fontSize: 13 }}>Delay Factors (cumulative days)</h3>
      </div>
      <div className="grid three-col-grid">
        {DELAY_FACTOR_FIELDS.map(([key, label]) => (
          <NumField key={key} id={`ms-${key}`} label={label} value={form[key]} onChange={(v) => set(key, v)} required />
        ))}
      </div>

      {isCompleting && (
        <>
          <DisclaimerBox warn>
            Marking this month "Completed" records the project's known FINAL outcome. These four fields are actual
            recorded results, never a model prediction or guess.
          </DisclaimerBox>
          <div className="grid three-col-grid">
            <NumField id="ms-fdd" label="Final Delay (days)" value={form.final_delay_days} onChange={(v) => set('final_delay_days', v)} required />
            <div className="field">
              <label htmlFor="ms-sig">Significant Delay?</label>
              <select id="ms-sig" className="select" required value={form.significant_delay} onChange={(e) => set('significant_delay', e.target.value)}>
                <option value="">Select…</option>
                <option value="1">Yes</option>
                <option value="0">No</option>
              </select>
            </div>
            <NumField id="ms-fcop" label="Final Cost Overrun (%)" value={form.final_cost_overrun_pct} onChange={(v) => set('final_cost_overrun_pct', v)} required />
            <div className="field">
              <label htmlFor="ms-co">Cost Overrun?</label>
              <select id="ms-co" className="select" required value={form.cost_overrun} onChange={(e) => set('cost_overrun', e.target.value)}>
                <option value="">Select…</option>
                <option value="1">Yes</option>
                <option value="0">No</option>
              </select>
            </div>
          </div>
        </>
      )}

      {submitState.status === 'error' && (
        <ErrorState
          title="Could not save this monthly update."
          message={submitState.error instanceof ApiError ? submitState.error.message : 'Unexpected error.'}
        />
      )}

      <div className="card-header" style={{ marginTop: 14 }}>
        <span />
        <button type="submit" className="btn btn-primary" disabled={submitState.status === 'loading'}>
          {submitState.status === 'loading' ? 'Saving…' : 'Save Monthly Update'}
        </button>
      </div>
    </form>
  )
}

function NumField({ id, label, value, onChange, required = false }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} className="input" type="number" step="0.01" required={required} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}
