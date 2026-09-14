import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectsCache } from '../context/ProjectsCacheContext'
import AsyncSection from './StateViews'
import { IconChevronRight } from './icons'

export default function ProjectPicker({ title, description, basePath, exampleProjectId = 'HRI-0006' }) {
  const { status, projects, error, reload } = useProjectsCache()
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const source = q
      ? projects.filter(
          (p) => p.project_id.toLowerCase().includes(q) || p.project_name.toLowerCase().includes(q)
        )
      : projects
    return source.slice(0, 25)
  }, [projects, query])

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
      </div>
      <div className="card card-padded">
        <div className="field" style={{ marginBottom: 14 }}>
          <label htmlFor="project-picker-input">Find a project</label>
          <input
            id="project-picker-input"
            className="input"
            style={{ width: '100%' }}
            placeholder={`Project ID or name (e.g. ${exampleProjectId})`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <AsyncSection
          status={status}
          error={error}
          data={filtered}
          onRetry={reload}
          loadingLabel="Loading projects…"
          errorTitle="Unable to load the project list."
          isEmpty={(d) => d.length === 0}
          emptyTitle="No matching projects."
          emptyMessage={`Try a different project ID or name, e.g. ${exampleProjectId}.`}
        >
          {(list) => (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {list.map((p) => (
                <li key={p.project_id}>
                  <button
                    type="button"
                    className="btn"
                    style={{ width: '100%', justifyContent: 'space-between' }}
                    onClick={() => navigate(basePath(p.project_id))}
                  >
                    <span>
                      <strong>{p.project_id}</strong> — {p.project_name} ({p.state})
                    </span>
                    <IconChevronRight size={15} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </AsyncSection>
      </div>
    </div>
  )
}
