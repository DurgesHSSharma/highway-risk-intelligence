import { useState } from 'react'
import { searchDocuments } from '../api/endpoints'
import { ApiError } from '../api/client'
import { ErrorState, EmptyState, LoadingState } from '../components/StateViews'
import EvidenceResultCard from '../components/EvidenceResultCard'
import DisclaimerBox from '../components/DisclaimerBox'
import { IconSearch } from '../components/icons'

// Real, hand-verified in-corpus questions from
// tests/fixtures/rag_test_questions.json -- not invented for the UI.
const EXAMPLE_QUESTIONS = [
  'What was the Delhi-Vadodara Expressway cost-benefit analysis compared against?',
  'How much money has NHAI raised through the Infrastructure Investment Trust InvIT mode?',
  'Why do some highway projects get stalled at the construction stage?',
  'In what year was the Bharatmala Pariyojana Phase-I approved by the central government?',
]

export default function DocumentSearch() {
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(5)
  const [state, setState] = useState({ status: 'idle', data: null, error: null })

  async function runSearch(q) {
    const value = (q ?? query).trim()
    if (!value) return
    setQuery(value)
    setState({ status: 'loading', data: null, error: null })
    try {
      const data = await searchDocuments(value, topK)
      setState({ status: 'success', data, error: null })
    } catch (err) {
      setState({ status: 'error', data: null, error: err })
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    runSearch()
  }

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>Document Search</h1>
          <p>Citation-grounded, extractive search over the real document corpus. No LLM is involved — answers are quoted directly from retrieved chunks.</p>
        </div>
      </div>

      <div className="card card-padded">
        <form onSubmit={handleSubmit} className="filter-bar" style={{ alignItems: 'flex-end' }}>
          <div className="field search-input-wrap">
            <label htmlFor="doc-search-input">Question</label>
            <input
              id="doc-search-input"
              className="input"
              style={{ width: '100%' }}
              placeholder="e.g. What was the Delhi-Vadodara Expressway cost-benefit analysis compared against?"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="doc-search-topk">Results</label>
            <select id="doc-search-topk" className="select" value={topK} onChange={(e) => setTopK(Number(e.target.value))}>
              {[3, 5, 10].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" className="btn btn-primary">
            <IconSearch size={15} /> Search
          </button>
        </form>

        <div style={{ marginTop: 12 }}>
          <span className="muted" style={{ fontSize: 11.5 }}>Example questions: </span>
          {EXAMPLE_QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              className="badge badge-info"
              style={{ marginRight: 6, marginTop: 6, cursor: 'pointer', border: 'none' }}
              onClick={() => runSearch(q)}
            >
              {q.length > 46 ? `${q.slice(0, 46)}…` : q}
            </button>
          ))}
        </div>
      </div>

      {state.status === 'loading' && (
        <div className="card card-padded">
          <LoadingState label="Searching the document corpus…" />
        </div>
      )}

      {state.status === 'error' && (
        <div className="card card-padded">
          <ErrorState
            title="Document search failed."
            message={state.error instanceof ApiError ? state.error.message : 'Unexpected error.'}
            onRetry={() => runSearch()}
          />
        </div>
      )}

      {state.status === 'success' && (
        <div className="card card-padded">
          <div className="card-header">
            <h2>Results for “{state.data.query}”</h2>
            <span className="badge badge-neutral">threshold {state.data.threshold}</span>
          </div>
          {state.data.not_found ? (
            <EmptyState
              title="Not found in the available documents."
              message="This corpus contains only 4 real public documents. A 'not found' result for an out-of-scope question is expected behavior."
            />
          ) : (
            <>
              <p className="evidence-text">{state.data.answer}</p>
              <div className="stack" style={{ gap: 10 }}>
                {state.data.results.map((r) => (
                  <EvidenceResultCard key={r.chunk_id} result={r} />
                ))}
              </div>
            </>
          )}
          <div style={{ marginTop: 14 }}>
            <DisclaimerBox>{state.data.corpus_disclaimer}</DisclaimerBox>
          </div>
        </div>
      )}
    </div>
  )
}
