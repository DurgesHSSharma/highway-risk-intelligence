import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useProjectsCache } from '../context/ProjectsCacheContext'
import AsyncSection from '../components/StateViews'
import Pagination from '../components/Pagination'
import RiskBadge from '../components/RiskBadge'
import { IconEye, IconSearch } from '../components/icons'
import { formatNumber } from '../utils/format'

const PAGE_SIZE_OPTIONS = [10, 20, 50]

export default function Projects() {
  const { status, projects, error, reload } = useProjectsCache()
  const [searchParams, setSearchParams] = useSearchParams()

  const [query, setQuery] = useState(searchParams.get('q') || '')
  const [state, setState] = useState('')
  const [projectType, setProjectType] = useState('')
  const [projectStatus, setProjectStatus] = useState('')
  const [sortKey, setSortKey] = useState('project_id')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  useEffect(() => {
    const q = searchParams.get('q')
    if (q) setQuery(q)
  }, [searchParams])

  const stateOptions = useMemo(() => [...new Set(projects.map((p) => p.state))].sort(), [projects])
  const typeOptions = useMemo(() => [...new Set(projects.map((p) => p.project_type))].sort(), [projects])
  const statusOptions = useMemo(() => [...new Set(projects.map((p) => p.current_status))].sort(), [projects])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    let result = projects.filter((p) => {
      if (q && !p.project_id.toLowerCase().includes(q) && !p.project_name.toLowerCase().includes(q)) return false
      if (state && p.state !== state) return false
      if (projectType && p.project_type !== projectType) return false
      if (projectStatus && p.current_status !== projectStatus) return false
      return true
    })
    result = [...result].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (typeof av === 'number' && typeof bv === 'number') return av - bv
      return String(av).localeCompare(String(bv))
    })
    return result
  }, [projects, query, state, projectType, projectStatus, sortKey])

  useEffect(() => {
    setPage(1)
  }, [query, state, projectType, projectStatus, pageSize])

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const currentPage = Math.min(page, totalPages)
  const pageItems = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize)

  function handleQueryChange(value) {
    setQuery(value)
    const next = new URLSearchParams(searchParams)
    if (value) next.set('q', value)
    else next.delete('q')
    setSearchParams(next, { replace: true })
  }

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Projects</h1>
          <p>Browse, search, and filter every project in the portfolio. Data is loaded from the HRI backend.</p>
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
                style={{ width: '100%', paddingLeft: 28 }}
                placeholder="Project ID or name"
                value={query}
                onChange={(e) => handleQueryChange(e.target.value)}
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="filter-state">State</label>
            <select id="filter-state" className="select" value={state} onChange={(e) => setState(e.target.value)}>
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
            <select id="filter-type" className="select" value={projectType} onChange={(e) => setProjectType(e.target.value)}>
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
            <select id="filter-status" className="select" value={projectStatus} onChange={(e) => setProjectStatus(e.target.value)}>
              <option value="">All statuses</option>
              {statusOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="sort-key">Sort by</label>
            <select id="sort-key" className="select" value={sortKey} onChange={(e) => setSortKey(e.target.value)}>
              <option value="project_id">Project ID</option>
              <option value="project_name">Project name</option>
              <option value="project_length_km">Length</option>
              <option value="original_contract_value_inr_cr">Contract value</option>
              <option value="state">State</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="page-size">Rows per page</label>
            <select id="page-size" className="select" value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>
              {PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </div>

        <AsyncSection
          status={status}
          error={error}
          data={pageItems}
          onRetry={reload}
          loadingLabel="Loading projects…"
          errorTitle="Unable to load project data."
          isEmpty={() => filtered.length === 0}
          emptyTitle="No projects match your filters."
          emptyMessage="Try clearing the search or filters above."
        >
          {(items) => (
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
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((p) => (
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
                          <Link className="icon-btn" to={`/projects/${p.project_id}`} aria-label={`View ${p.project_id}`}>
                            <IconEye size={15} />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={currentPage} pageSize={pageSize} total={filtered.length} onPageChange={setPage} />
            </>
          )}
        </AsyncSection>
      </div>
    </div>
  )
}
