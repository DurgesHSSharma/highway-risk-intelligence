import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ProjectDetails from './ProjectDetails'
import { ApiError } from '../api/client'
import { archiveProject, addProjectSnapshot, getProject, listProjectSnapshots, reactivateProject } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  getProject: vi.fn(),
  listProjectSnapshots: vi.fn(),
  archiveProject: vi.fn(),
  reactivateProject: vi.fn(),
  addProjectSnapshot: vi.fn(),
}))

function renderAt(projectId) {
  return render(
    <MemoryRouter initialEntries={[`/projects/${projectId}`]}>
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectDetails />} />
        <Route path="/projects/:projectId/edit" element={<div>edit project page</div>} />
      </Routes>
    </MemoryRouter>
  )
}

const BASE_PROJECT = {
  project_id: 'HRI-0006',
  data_provenance: 'SYNTHETIC',
  project_name: 'Delhi-Dehradun Expressway',
  highway_number: 'NH-58',
  state: 'Uttarakhand',
  project_type: 'Expressway',
  contractor: 'ACME Infra',
  project_length_km: 210.4,
  original_contract_value_inr_cr: 4500,
  planned_start_date: '2021-01-01',
  planned_completion_date: '2024-12-31',
  planned_duration_months: 48,
  current_status: 'Ongoing',
  is_archived: false,
  archived_at: null,
}

describe('ProjectDetails page', () => {
  it('shows an explicit not-found state for an unknown project ID (never a blank screen)', async () => {
    getProject.mockRejectedValue(new ApiError("Project 'HRI-9999' not found.", { status: 404 }))
    listProjectSnapshots.mockResolvedValue([])

    renderAt('HRI-9999')

    expect(await screen.findByText('Project "HRI-9999" was not found.')).toBeInTheDocument()
  })

  it('renders project info and the latest snapshot once loaded', async () => {
    getProject.mockResolvedValue({
      project_id: 'HRI-0006',
      data_provenance: 'synthetic',
      project_name: 'Delhi-Dehradun Expressway',
      highway_number: 'NH-58',
      state: 'Uttarakhand',
      project_type: 'Expressway',
      contractor: 'ACME Infra',
      project_length_km: 210.4,
      original_contract_value_inr_cr: 4500,
      planned_start_date: '2021-01-01',
      planned_completion_date: '2024-12-31',
      planned_duration_months: 48,
      current_status: 'Ongoing',
    })
    listProjectSnapshots.mockResolvedValue([
      {
        project_id: 'HRI-0006',
        reporting_month: '2022-12',
        months_since_start: 24,
        project_status: 'Ongoing',
        is_terminal_snapshot: false,
        planned_physical_progress_pct: 55,
        actual_physical_progress_pct: 48,
        physical_progress_variance_pct: -7,
        planned_financial_progress_pct: 50,
        actual_financial_progress_pct: 44,
        financial_progress_variance_pct: -6,
        planned_cost_to_date_inr_cr: 2000,
        actual_cost_to_date_inr_cr: 1800,
        actual_expenditure_inr_cr: 300,
        material_cost_inr_cr: 100,
        labour_cost_inr_cr: 80,
        equipment_cost_inr_cr: 40,
        delay_related_cost_inr_cr: 20,
        land_acquisition_delay_days: 40,
        utility_shifting_delay_days: 10,
        environment_clearance_delay_days: 5,
        material_delay_days: 3,
        labour_shortage_days: 0,
        equipment_unavailability_days: 0,
        weather_disruption_days: 8,
        traffic_diversion_delay_days: 2,
        design_change_delay_days: 0,
        approval_delay_days: 6,
        contractor_productivity_factor: 0.98,
      },
    ])

    renderAt('HRI-0006')

    expect(await screen.findByText(/Delhi-Dehradun Expressway/)).toBeInTheDocument()
    expect(screen.getByText('ACME Infra')).toBeInTheDocument()
    expect(screen.getByText('Land Acquisition')).toBeInTheDocument()
  })

  it('navigates to the edit page', async () => {
    getProject.mockResolvedValue(BASE_PROJECT)
    listProjectSnapshots.mockResolvedValue([])

    renderAt('HRI-0006')
    fireEvent.click(await screen.findByRole('button', { name: /^edit$/i }))

    expect(await screen.findByText('edit project page')).toBeInTheDocument()
  })

  it('shows an insufficient-data state with a call to action when there are no snapshots yet', async () => {
    getProject.mockResolvedValue(BASE_PROJECT)
    listProjectSnapshots.mockResolvedValue([])

    renderAt('HRI-0006')

    expect(await screen.findByText('Insufficient data for model assessment.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add monthly update/i })).toBeInTheDocument()
  })

  it('archives an active project', async () => {
    getProject.mockResolvedValue(BASE_PROJECT)
    listProjectSnapshots.mockResolvedValue([])
    archiveProject.mockResolvedValue({ ...BASE_PROJECT, is_archived: true, archived_at: '2026-01-01T00:00:00' })

    renderAt('HRI-0006')
    fireEvent.click(await screen.findByRole('button', { name: /^archive$/i }))

    await waitFor(() => expect(archiveProject).toHaveBeenCalledWith('HRI-0006'))
  })

  it('reactivates an archived project', async () => {
    getProject.mockResolvedValue({ ...BASE_PROJECT, is_archived: true, archived_at: '2026-01-01T00:00:00' })
    listProjectSnapshots.mockResolvedValue([])
    reactivateProject.mockResolvedValue({ ...BASE_PROJECT, is_archived: false, archived_at: null })

    renderAt('HRI-0006')
    fireEvent.click(await screen.findByRole('button', { name: /^reactivate$/i }))

    await waitFor(() => expect(reactivateProject).toHaveBeenCalledWith('HRI-0006'))
  })

  it('submits a first monthly update from the insufficient-data state', async () => {
    getProject.mockResolvedValue(BASE_PROJECT)
    listProjectSnapshots.mockResolvedValue([])
    addProjectSnapshot.mockResolvedValue({ reporting_month: '2025-06' })

    const { container } = renderAt('HRI-0006')
    fireEvent.click(await screen.findByRole('button', { name: /add monthly update/i }))

    fireEvent.change(screen.getByLabelText('Reporting Month'), { target: { value: '2025-06' } })
    fireEvent.change(screen.getByLabelText('Planned Physical Progress (%)'), { target: { value: '20' } })
    fireEvent.change(screen.getByLabelText('Actual Physical Progress (%)'), { target: { value: '18' } })
    fireEvent.change(screen.getByLabelText('Planned Financial Progress (%)'), { target: { value: '20' } })
    fireEvent.change(screen.getByLabelText('Planned Cost to Date'), { target: { value: '900' } })
    fireEvent.change(screen.getByLabelText('Actual Cost to Date'), { target: { value: '800' } })
    fireEvent.change(screen.getByLabelText('Material Cost'), { target: { value: '400' } })
    fireEvent.change(screen.getByLabelText('Labour Cost'), { target: { value: '300' } })
    fireEvent.change(screen.getByLabelText('Equipment Cost'), { target: { value: '100' } })
    fireEvent.change(screen.getByLabelText('Delay-Related Cost'), { target: { value: '10' } })

    fireEvent.submit(container.querySelector('form'))

    await waitFor(() => expect(addProjectSnapshot).toHaveBeenCalledTimes(1))
    expect(addProjectSnapshot.mock.calls[0][0]).toBe('HRI-0006')
    expect(addProjectSnapshot.mock.calls[0][1]).toMatchObject({ reporting_month: '2025-06', project_status: 'Ongoing' })
  })
})
