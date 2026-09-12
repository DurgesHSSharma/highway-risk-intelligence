import { useEffect, useState } from 'react'
import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

function App() {
  const [status, setStatus] = useState('checking')
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE_URL}/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data) => {
        if (cancelled) return
        setStatus('connected')
        setDetail(data)
      })
      .catch((err) => {
        if (cancelled) return
        setStatus('error')
        setDetail({ message: err.message })
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="health-panel">
      <h1>Highway Risk Intelligence</h1>
      <p className="subtitle">
        Prototype decision-support system inspired by highway infrastructure
        project monitoring.
      </p>

      <div className={`status-card status-${status}`}>
        <span className="status-label">Backend status:</span>
        <span className="status-value">{status}</span>
      </div>

      {detail && (
        <pre className="status-detail">{JSON.stringify(detail, null, 2)}</pre>
      )}

      <p className="hint">
        Backend expected at <code>{API_BASE_URL}</code>
      </p>
    </main>
  )
}

export default App
