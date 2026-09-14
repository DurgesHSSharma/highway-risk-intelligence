import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Generic loading/success/error/empty data-fetching hook used by every
 * API-driven page. `fetcher` receives an AbortSignal and must return a
 * Promise. Re-runs whenever `deps` changes; `reload()` lets a page (e.g. a
 * "Retry" button) re-run it on demand. Pass `skip: true` (e.g. while a
 * required param like a reporting month hasn't been derived yet) to hold
 * off making any request -- status stays 'idle' until skip becomes false.
 */
export function useApi(fetcher, deps = [], { skip = false } = {}) {
  const [status, setStatus] = useState(skip ? 'idle' : 'loading')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const [reloadToken, setReloadToken] = useState(0)
  const reload = useCallback(() => setReloadToken((t) => t + 1), [])

  useEffect(() => {
    if (skip) {
      setStatus('idle')
      return undefined
    }

    const controller = new AbortController()
    let cancelled = false

    setStatus('loading')
    setError(null)

    fetcherRef.current(controller.signal)
      .then((result) => {
        if (cancelled) return
        setData(result)
        setStatus('success')
      })
      .catch((err) => {
        if (cancelled || err?.name === 'AbortError') return
        setError(err)
        setStatus('error')
      })

    return () => {
      cancelled = true
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skip, ...deps, reloadToken])

  return {
    status,
    data,
    error,
    reload,
    isLoading: status === 'loading' || status === 'idle',
    isError: status === 'error',
  }
}
