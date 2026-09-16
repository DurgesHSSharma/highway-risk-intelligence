import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ProjectForm from './ProjectForm'
import { ApiError } from '../api/client'
import { createProject, getProject, updateProject } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  createProject: vi.fn(),
  updateProject: vi.fn(),
  getProject: vi.fn(),
}))

function renderCreate() {
  return render(
    <MemoryRouter initialEntries={['/projects/new']}>
      <Routes>
        <Route path="/projects/new" element={<ProjectForm />} />
        <Route path="/projects/:projectId" element={<div>project details page</div>} />
      </Routes>
    </MemoryRouter>
  )
}

function renderEdit(projectId) {
  return render(
    <MemoryRouter initialEntries={[`/projects/${projectId}/edit`]}>
      <Routes>
        <Route path="/projects/:projectId/edit" element={<ProjectForm />} />
        <Route path="/projects/:projectId" element={<div>project details page</div>} />
      </Routes>
    </MemoryRouter>
  )
}

// jsdom does not reliably run native HTML5 constraint validation the way a
// real browser does (especially for type="date" inputs), so a plain
// fireEvent.click on the submit button can silently no-op. Submitting the
// <form> element directly exercises this component's own onSubmit handler
// -- the thing these tests actually care about -- without depending on
// jsdom's imperfect native-validation behavior.
function submitForm(container) {
  fireEvent.submit(container.querySelector('form'))
}

function fillRequiredFields() {
  fireEvent.change(screen.getByLabelText('Project Name'), { target: { value: 'Test Highway' } })
  fireEvent.change(screen.getByLabelText('Highway Number'), { target: { value: 'NH-101' } })
  fireEvent.change(screen.getByLabelText('State'), { target: { value: 'Test State' } })
  fireEvent.change(screen.getByLabelText('Project Type'), { target: { value: 'Greenfield' } })
  fireEvent.change(screen.getByLabelText('Length (km)'), { target: { value: '25' } })
  fireEvent.change(screen.getByLabelText('Original Contract Value (INR Cr)'), { target: { value: '250' } })
  fireEvent.change(screen.getByLabelText('Planned Start Date'), { target: { value: '2025-01-01' } })
  fireEvent.change(screen.getByLabelText('Planned Completion Date'), { target: { value: '2027-01-01' } })
  fireEvent.change(screen.getByLabelText('Planned Duration (months)'), { target: { value: '24' } })
}

describe('ProjectForm page', () => {
  it('renders the create form with an empty, optional project ID field', () => {
    renderCreate()
    expect(screen.getByText('Add New Project')).toBeInTheDocument()
    expect(screen.getByLabelText('Project ID (optional)')).toHaveValue('')
  })

  it('submits a new project and navigates to its details page', async () => {
    createProject.mockResolvedValue({ project_id: 'HRI-0401' })
    const { container } = renderCreate()

    fillRequiredFields()
    submitForm(container)

    await waitFor(() => expect(createProject).toHaveBeenCalledTimes(1))
    expect(createProject.mock.calls[0][0]).toMatchObject({
      project_name: 'Test Highway',
      highway_number: 'NH-101',
      project_length_km: 25,
      original_contract_value_inr_cr: 250,
      planned_duration_months: 24,
    })
    expect(await screen.findByText('project details page')).toBeInTheDocument()
  })

  it('shows a clear error when creation fails (e.g. duplicate project ID)', async () => {
    createProject.mockRejectedValue(new ApiError("Project 'HRI-0401' already exists.", { status: 409 }))
    const { container } = renderCreate()

    fillRequiredFields()
    submitForm(container)

    expect(await screen.findByText("Project 'HRI-0401' already exists.")).toBeInTheDocument()
  })

  it('hydrates the edit form from the existing project and submits only an update', async () => {
    getProject.mockResolvedValue({
      project_id: 'HRI-0006',
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
    })
    updateProject.mockResolvedValue({ project_id: 'HRI-0006' })

    const { container } = renderEdit('HRI-0006')

    expect(await screen.findByDisplayValue('Delhi-Dehradun Expressway')).toBeInTheDocument()
    // project_id is not editable in edit mode.
    expect(screen.queryByLabelText('Project ID (optional)')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Contractor'), { target: { value: 'New Contractor' } })
    submitForm(container)

    await waitFor(() => expect(updateProject).toHaveBeenCalledWith('HRI-0006', expect.objectContaining({ contractor: 'New Contractor' })))
    expect(await screen.findByText('project details page')).toBeInTheDocument()
  })
})
