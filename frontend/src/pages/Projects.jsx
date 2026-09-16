import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useProjectsCache } from '../context/ProjectsCacheContext'
import { useApi } from '../hooks/useApi'
import { archiveProject, listProjects, reactivateProject } from '../api/endpoints'
import AsyncSection from '../components/StateViews'
import Pagination from '../components/Pagination'
import RiskBadge from '../components/RiskBadge'
import { IconArchive, IconEdit, IconEye, IconPlus, IconSearch, IconX } from '../components/icons'
import { formatNumber } from '../utils/format'

const PAGE_SIZE_OPTIONS = [10, 20, 50]
const SEARCH_DEBOUNCE_MS = 300

export default function Projects() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  // The free-text query is debounced before it becomes a real backend
  // request, so fast typing doesn't fire a request per keystroke; every
  // other control (state/type/status/archived/page size) takes effect
  // immediately.
  const [query, setQuery] = useState(searchParams.get('q') || '')
  const [debouncedQuery, setDebouncedQuery] = useState(query)
  const [state, setState] = useState('')
  const [projectType, setProjectType] = useState('')
  const [projectStatus, setProjectStatus] = useState('')
  const [archivedFilter, setArchivedFilter] = useState('') // '', 'active', 'archived'
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [actionState, setActionState] = useState({ projectId: null, status: 'idle', error: null })

  // Resets to page 1 in the SAME state update as the debounced query
  // change (React batches both) rather than in a separate effect reacting
  // to `debouncedQuery` -- a separate effect would run one render late,
  // firing one avoidable backend request at the stale page number before
  // correcting itself. Every other filter below resets the page the same
  // way, inline in its own onChange.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query)
      setPage(1)
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [query])

  // Filter-dropdown *option lists* only (never the search/filter results
  // themselves) are sourced from the app-wide ProjectsCacheContext, which
  // Dashboard/Analytics already hydrate once per session regardless of
  // whether this page uses it -- this reuses that existing fetch instead of
  // issuing a second one, and is not itself a full-list search fallback.
  const { projects: cachedProjects } = useProjectsCache()
  const stateOptions = useMemo(() => [...new Set(cachedProjects.map((p) => p.state))].sort(), [cachedProjects])
  const typeOptions = useMemo(() => [...new Set(cachedProjects.map((p) => p.project_type))].sort(), [cachedProjects])
  const statusOptions = useMemo(() => [...new Set(cachedProjects.map((p) => p.current_status))].sort(), [cachedProjects])

  // The actual table data: one real backend call per page/search/filter
  // change, performed in SQL server-side -- never a client-side filter over
  // a pre-fetched full project list.
  const result = useApi(
    (signal) =>
      listProjects(
        {
          page,
          page_size: pageSize,
          q: debouncedQuery,
          state,
          project_type: projectType,
          project_status: projectStatus,
          is_archived: archivedFilter === '' ? undefined : archivedFilter === 'archived',
        },
        signal
      ),
    [page, pageSize, debouncedQuery, state, projectType, projectStatus, archivedFilter]
  )

  function handleQueryChange(value) {
    setQuery(value)
    const next = new URLSearchParams(searchParams)
    if (value) next.set('q', value)
    else next.delete('q')
    setSearchParams(next, { replace: true })
  }

  async function handleToggleArchive(project) {
    setActionState({ projectId: project.project_id, status: 'loading', error: null })
    try {
      if (project.is_archived) {
        await reactivateProject(project.project_id)
      } else {
        await archiveProject(project.project_id)
      }
      setActionState({ projectId: null, status: 'idle', error: null })
      result.reload()
    } catch (err) {
      setActionState({ projectId: project.project_id, status: 'error', error: err })
    }
  }

  const items = result.data?.items ?? []
  const total = result.data?.total ?? 0

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Projects</h1>
          <p>Browse, search, and filter every project in the portfolio. Search and filters run on the HRI backend.</p>
        </div>
        <div className="page-header-actions">
          <button type="button" className="btn btn-primary" onClick={() => navigate('/projects/new')}>
            <IconPlus size={15} /> Add Project
          </button>
        </div>
      </div>

      <div className="card card-padded">
        <div className="filter-bar">
          <div className="field search-input-wrap">
            <label htmlFor="projects-search">Search</label>
            <div style={{ position: 'relative' }}>
              <span style={{ position: 'absolute', left: 9, top: 9, color: 'var(--text-muted)' }}>
                <IconSearch size={14} />
              </span>
              <input
                id="projects-search"
                className="input"
                style={{ width: '100%', paddingLeft: 28, paddingRight: query ? 28 : undefined }}
                placeholder="Project ID, name, highway, state, contractor, or type"
                value={query}
                onChange={(e) => handleQueryChange(e.target.value)}
              />
              {query && (
                <button
                  type="button"
                  aria-label="Clear search"
                  className="icon-btn"
                  style={{ position: 'absolute', right: 4, top: 4 }}
                  onClick={() => handleQueryChange('')}
                >
                  <IconX size={13} />
                </button>
              )}
            </div>
          </div>
          <div className="field">
            <label htmlFor="filter-state">State</label>
            <select
              id="filter-state"
              className="select"
              value={state}
              onChange={(e) => {
                setState(e.target.value)
                setPage(1)
              }}
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
            <label htmlFor="filter-type">Project type</label>
            <select
              id="filter-type"
              className="select"
              value={projectType}
              onChange={(e) => {
                setProjectType(e.target.value)
                setPage(1)
              }}
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
            <label htmlFor="filter-status">Status</label>
            <select
              id="filter-status"
              className="select"
              value={projectStatus}
              onChange={(e) => {
                setProjectStatus(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All statuses</option>
              {statusOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="filter-archived">Lifecycle</label>
            <select
              id="filter-archived"
              className="select"
              value={archivedFilter}
              onChange={(e) => {
                setArchivedFilter(e.target.value)
                setPage(1)
              }}
            >
              <option value="">Active + archived</option>
              <option value="active">Active only</option>
              <option value="archived">Archived only</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="page-size">Rows per page</label>
            <select
              id="page-size"
              className="select"
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value))
                setPage(1)
              }}
            >
              {PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </div>

        <AsyncSection
          status={result.status}
          error={result.error}
          data={items}
          onRetry={result.reload}
          loadingLabel="Loading projects…"
          errorTitle="Unable to load project data."
          isEmpty={(d) => d.length === 0}
          emptyTitle="No projects match your search or filters."
          emptyMessage="Try clearing the search or filters above."
        >
          {(rows) => (
            <>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Project ID</th>
                      <th>Project Name</th>
                      <th>State</th>
                      <th>Type</th>
                      <th>Length (km)</th>
                      <th>Contract Value (Cr)</th>
                      <th>Status</th>
                      <th>Lifecycle</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((p) => (
                      <tr key={p.project_id}>
                        <td>
                          <Link className="table-id" to={`/projects/${p.project_id}`}>
                            {p.project_id}
                          </Link>
                        </td>
                        <td>{p.project_name}</td>
                        <td>{p.state}</td>
                        <td>{p.project_type}</td>
                        <td>{formatNumber(p.project_length_km, 1)}</td>
                        <td>{formatNumber(p.original_contract_value_inr_cr, 0)}</td>
                        <td>
                          <RiskBadge level={p.current_status === 'Completed' ? 'low' : 'medium'} label={p.current_status} />
                        </td>
                        <td>
                          {p.is_archived ? (
                            <span className="badge badge-neutral">Archived</span>
                          ) : (
                            <span className="badge badge-info">Active</span>
                          )}
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: 6 }}>
                            <Link className="icon-btn" to={`/projects/${p.project_id}`} aria-label={`View ${p.project_id}`}>
                              <IconEye size={15} />
                            </Link>
                            <Link className="icon-btn" to={`/projects/${p.project_id}/edit`} aria-label={`Edit ${p.project_id}`}>
                              <IconEdit size={15} />
                            </Link>
                            <button
                              type="button"
                              className="icon-btn"
                              aria-label={p.is_archived ? `Reactivate ${p.project_id}` : `Archive ${p.project_id}`}
                              title={p.is_archived ? 'Reactivate' : 'Archive'}
                              disabled={actionState.projectId === p.project_id && actionState.status === 'loading'}
                              onClick={() => handleToggleArchive(p)}
                            >
                              <IconArchive size={15} />
                            </button>
                          </div>
                          {actionState.projectId === p.project_id && actionState.status === 'error' && (
                            <div className="muted" style={{ fontSize: 11, color: 'var(--danger, #c0392b)' }}>
                              {actionState.error?.message || 'Action failed.'}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} />
            </>
          )}
        </AsyncSection>
      </div>
    </div>
  )
}
