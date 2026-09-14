import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { listProjects } from '../api/endpoints'

const PAGE_SIZE = 100

const ProjectsCacheContext = createContext(null)

/**
 * Hydrates the full project list once per session (GET /projects has a
 * max page_size of 100, so this issues a handful of paginated calls, not
 * one per project) and shares it across Dashboard/Projects/Analytics so
 * those pages don't each re-fetch the same data. This is what backs the
 * Projects page's client-side search/sort/filter -- the backend has no
 * free-text search param on /projects, so the alternative would be a
 * fabricated search backend, which the brief explicitly disallows.
 */
export function ProjectsCacheProvider({ children }) {
  const [state, setState] = useState({ status: 'loading', projects: [], total: 0, error: null })

  const load = useCallback(() => {
    let cancelled = false
    const controller = new AbortController()
    setState((s) => ({ ...s, status: 'loading', error: null }))

    async function run() {
      try {
        const first = await listProjects({ page: 1, page_size: PAGE_SIZE }, controller.signal)
        let all = [...first.items]
        const totalPages = Math.max(1, Math.ceil(first.total / PAGE_SIZE))
        for (let page = 2; page <= totalPages; page += 1) {
          const next = await listProjects({ page, page_size: PAGE_SIZE }, controller.signal)
          all = all.concat(next.items)
        }
        if (cancelled) return
        setState({ status: 'success', projects: all, total: first.total, error: null })
      } catch (err) {
        if (cancelled || err?.name === 'AbortError') return
        setState({ status: 'error', projects: [], total: 0, error: err })
      }
    }

    run()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [])

  useEffect(() => load(), [load])

  return (
    <ProjectsCacheContext.Provider value={{ ...state, reload: load }}>{children}</ProjectsCacheContext.Provider>
  )
}

export function useProjectsCache() {
  const ctx = useContext(ProjectsCacheContext)
  if (!ctx) throw new Error('useProjectsCache must be used within ProjectsCacheProvider')
  return ctx
}
