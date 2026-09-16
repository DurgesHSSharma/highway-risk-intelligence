import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { createProject, getProject, updateProject } from '../api/endpoints'
import { ApiError } from '../api/client'
import AsyncSection, { ErrorState } from '../components/StateViews'
import { IconEdit, IconPlus } from '../components/icons'

// Shared create/edit form for the Phase 17B project lifecycle write
// endpoints (POST /projects, PATCH /projects/{id}). Field set mirrors
// backend/app/schemas/project_lifecycle.py's ProjectCreate/ProjectUpdate
// exactly -- no field invented here that the backend doesn't also accept.
const EMPTY_FORM = {
  project_id: '',
  project_name: '',
  highway_number: '',
  state: '',
  project_type: '',
  contractor: '',
  project_length_km: '',
  original_contract_value_inr_cr: '',
  planned_start_date: '',
  planned_completion_date: '',
  planned_duration_months: '',
}

function projectToForm(p) {
  return {
    project_id: p.project_id,
    project_name: p.project_name,
    highway_number: p.highway_number,
    state: p.state,
    project_type: p.project_type,
    contractor: p.contractor || '',
    project_length_km: String(p.project_length_km),
    original_contract_value_inr_cr: String(p.original_contract_value_inr_cr),
    planned_start_date: p.planned_start_date,
    planned_completion_date: p.planned_completion_date,
    planned_duration_months: String(p.planned_duration_months),
  }
}

export default function ProjectForm() {
  const { projectId } = useParams()
  const isEdit = Boolean(projectId)
  const navigate = useNavigate()

  const existing = useApi((signal) => getProject(projectId, signal), [projectId], { skip: !isEdit })

  const [form, setForm] = useState(EMPTY_FORM)
  const [hydrated, setHydrated] = useState(!isEdit)
  const [submitState, setSubmitState] = useState({ status: 'idle', error: null })

  useEffect(() => {
    if (isEdit && existing.status === 'success' && existing.data && !hydrated) {
      setForm(projectToForm(existing.data))
      setHydrated(true)
    }
  }, [isEdit, existing.status, existing.data, hydrated])

  function handleChange(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  function buildPayload() {
    const numeric = (v) => (v === '' ? undefined : Number(v))
    if (isEdit) {
      return {
        project_name: form.project_name,
        highway_number: form.highway_number,
        state: form.state,
        project_type: form.project_type,
        contractor: form.contractor || null,
        project_length_km: numeric(form.project_length_km),
        original_contract_value_inr_cr: numeric(form.original_contract_value_inr_cr),
        planned_start_date: form.planned_start_date,
        planned_completion_date: form.planned_completion_date,
        planned_duration_months: numeric(form.planned_duration_months),
      }
    }
    return {
      project_id: form.project_id.trim() || null,
      project_name: form.project_name,
      highway_number: form.highway_number,
      state: form.state,
      project_type: form.project_type,
      contractor: form.contractor || null,
      project_length_km: numeric(form.project_length_km),
      original_contract_value_inr_cr: numeric(form.original_contract_value_inr_cr),
      planned_start_date: form.planned_start_date,
      planned_completion_date: form.planned_completion_date,
      planned_duration_months: numeric(form.planned_duration_months),
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitState({ status: 'loading', error: null })
    try {
      if (isEdit) {
        await updateProject(projectId, buildPayload())
        setSubmitState({ status: 'idle', error: null })
        navigate(`/projects/${projectId}`)
      } else {
        const created = await createProject(buildPayload())
        setSubmitState({ status: 'idle', error: null })
        navigate(`/projects/${created.project_id}`)
      }
    } catch (err) {
      setSubmitState({ status: 'error', error: err })
    }
  }

  if (isEdit && existing.status === 'error' && existing.error?.status === 404) {
    return <ErrorState title={`Project "${projectId}" was not found.`} />
  }

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>{isEdit ? `Edit ${projectId}` : 'Add New Project'}</h1>
          <p>
            {isEdit
              ? "Update this project's government/project estimate information. Monthly progress is recorded separately."
              : 'Records the initial government/project estimate. No ML assessment is possible until at least one monthly progress update is added.'}
          </p>
        </div>
      </div>

      {isEdit ? (
        <AsyncSection
          status={existing.status}
          error={existing.error}
          data={existing.data}
          onRetry={existing.reload}
          loadingLabel="Loading project…"
          errorTitle="Unable to load this project."
        >
          {() => <ProjectFormFields {...{ form, handleChange, handleSubmit, isEdit, submitState }} />}
        </AsyncSection>
      ) : (
        <ProjectFormFields {...{ form, handleChange, handleSubmit, isEdit, submitState }} />
      )}
    </div>
  )
}

function ProjectFormFields({ form, handleChange, handleSubmit, isEdit, submitState }) {
  return (
    <form className="card card-padded" onSubmit={handleSubmit}>
      <div className="card-header">
        <h2>Project Information</h2>
      </div>
      <div className="grid two-col-grid">
        {!isEdit && (
          <div className="field">
            <label htmlFor="pf-project-id">Project ID (optional)</label>
            <input
              id="pf-project-id"
              className="input"
              placeholder="Auto-generated if left blank, e.g. HRI-0401"
              value={form.project_id}
              onChange={(e) => handleChange('project_id', e.target.value)}
            />
          </div>
        )}
        <div className="field">
          <label htmlFor="pf-name">Project Name</label>
          <input
            id="pf-name"
            className="input"
            required
            value={form.project_name}
            onChange={(e) => handleChange('project_name', e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="pf-highway">Highway Number</label>
          <input
            id="pf-highway"
            className="input"
            required
            value={form.highway_number}
            onChange={(e) => handleChange('highway_number', e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="pf-state">State</label>
          <input
            id="pf-state"
            className="input"
            required
            value={form.state}
            onChange={(e) => handleChange('state', e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="pf-type">Project Type</label>
          <input
            id="pf-type"
            className="input"
            required
            value={form.project_type}
            onChange={(e) => handleChange('project_type', e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="pf-contractor">Contractor</label>
          <input
            id="pf-contractor"
            className="input"
            value={form.contractor}
            onChange={(e) => handleChange('contractor', e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="pf-length">Length (km)</label>
          <input
            id="pf-length"
            className="input"
            type="number"
            min="0.1"
            step="0.1"
            required
            value={form.project_length_km}
            onChange={(e) => handleChange('project_length_km', e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="pf-contract-value">Original Contract Value (INR Cr)</label>
          <input
            id="pf-contract-value"
            className="input"
            type="number"
            min="0.01"
            step="0.01"
            required
            value={form.original_contract_value_inr_cr}
            onChange={(e) => handleChange('original_contract_value_inr_cr', e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="pf-start">Planned Start Date</label>
          <input
            id="pf-start"
            className="input"
            type="date"
            required
            value={form.planned_start_date}
            onChange={(e) => handleChange('planned_start_date', e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="pf-completion">Planned Completion Date</label>
          <input
            id="pf-completion"
            className="input"
            type="date"
            required
            value={form.planned_completion_date}
            onChange={(e) => handleChange('planned_completion_date', e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="pf-duration">Planned Duration (months)</label>
          <input
            id="pf-duration"
            className="input"
            type="number"
            min="1"
            step="1"
            required
            value={form.planned_duration_months}
            onChange={(e) => handleChange('planned_duration_months', e.target.value)}
          />
        </div>
      </div>

      {submitState.status === 'error' && (
        <ErrorState
          title="Could not save this project."
          message={submitState.error instanceof ApiError ? submitState.error.message : 'Unexpected error.'}
        />
      )}

      <div className="card-header" style={{ marginTop: 14 }}>
        <span />
        <button type="submit" className="btn btn-primary" disabled={submitState.status === 'loading'}>
          {isEdit ? <IconEdit size={15} /> : <IconPlus size={15} />}
          {submitState.status === 'loading' ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Project'}
        </button>
      </div>
    </form>
  )
}
