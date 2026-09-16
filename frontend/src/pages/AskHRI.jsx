import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { askHRI } from '../api/endpoints'
import { ApiError } from '../api/client'
import DisclaimerBox from '../components/DisclaimerBox'
import { IconAlertTriangle, IconChat, IconInfo } from '../components/icons'
import { formatPercent, formatDays } from '../utils/format'

// Phase 17C "Ask HRI": a deterministic intent/tool-routing query
// interface (app.agent.router on the backend), presented as a simple
// message thread -- deliberately NOT styled like a general-purpose AI
// chatbot (no streaming/typing animation, no persona), since the backend
// is not an LLM and must not be visually misrepresented as one. Every
// assistant reply is labeled with its answer_type and, where applicable,
// carries real citations and disclaimers straight from the backend.

const ANSWER_TYPE_META = {
  actual: { label: 'Actual recorded data', className: 'badge-info' },
  prediction: { label: 'Model prediction', className: 'badge-medium' },
  hypothetical: { label: 'Hypothetical (what-if)', className: 'badge-neutral' },
  document_evidence: { label: 'Document evidence', className: 'badge-info' },
  support: { label: 'App guidance', className: 'badge-neutral' },
  unsupported: { label: 'Not answered', className: 'badge-neutral' },
}

const EXAMPLE_QUERIES = [
  'Show me information about HRI-0006',
  'Why is HRI-0006 high risk?',
  'Which projects have high delay risk?',
  'What is the risk distribution by state?',
  'What do the documents say about cost escalation?',
  'What happens if progress improves by 10% for HRI-0006?',
  'How do I archive a project?',
]

export default function AskHRI() {
  const [searchParams] = useSearchParams()
  const contextProjectId = searchParams.get('project')
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([])
  const [sending, setSending] = useState(false)
  const threadRef = useRef(null)

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  async function sendMessage(text) {
    const trimmed = text.trim()
    if (!trimmed || sending) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', text: trimmed }])
    setSending(true)
    try {
      const response = await askHRI(trimmed, contextProjectId)
      setMessages((prev) => [...prev, { role: 'assistant', response }])
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'assistant', error: err }])
    } finally {
      setSending(false)
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    sendMessage(input)
  }

  return (
    <div className="stack">
      <div className="page-header">
        <div>
          <h1>
            <IconChat size={19} style={{ marginRight: 8, verticalAlign: '-3px' }} />
            Ask HRI
          </h1>
          <p>
            A deterministic query router over HRI's own project data, predictions, documents, and simulator --
            not a general-purpose AI. Every reply is labeled by type (actual data, model prediction, hypothetical
            what-if, document evidence, app guidance, or not answered) and cites its real source where applicable.
          </p>
          {contextProjectId && (
            <span className="badge badge-info" style={{ marginTop: 6, display: 'inline-flex' }}>
              Context: {contextProjectId}
            </span>
          )}
        </div>
      </div>

      <div className="card card-padded" style={{ display: 'flex', flexDirection: 'column', minHeight: 440 }}>
        <div ref={threadRef} className="ask-hri-thread" role="log" aria-live="polite">
          {messages.length === 0 && (
            <div className="stack" style={{ gap: 6 }}>
              <p className="muted" style={{ fontSize: 13 }}>Try one of these, or type your own question:</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {EXAMPLE_QUERIES.map((q) => (
                  <button key={q} type="button" className="btn btn-sm" onClick={() => sendMessage(q)}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) =>
            m.role === 'user' ? (
              <div key={i} className="ask-hri-message ask-hri-message-user">
                {m.text}
              </div>
            ) : (
              <AssistantMessage key={i} entry={m} />
            )
          )}

          {sending && (
            <div className="ask-hri-message ask-hri-message-assistant muted" role="status">
              <span className="spinner" /> HRI is looking that up…
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 8, marginTop: 14 }}>
          <input
            className="input"
            style={{ flex: 1 }}
            placeholder="Ask about a project, risk, analytics, documents, a what-if, or how to use HRI…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            aria-label="Ask HRI"
          />
          <button type="submit" className="btn btn-primary" disabled={sending || !input.trim()}>
            Send
          </button>
        </form>
      </div>
    </div>
  )
}

function AssistantMessage({ entry }) {
  if (entry.error) {
    return (
      <div className="ask-hri-message ask-hri-message-assistant">
        <div className="state-block compact" role="alert" style={{ padding: 0 }}>
          <span className="state-icon">
            <IconAlertTriangle size={20} />
          </span>
          <span className="state-title">HRI couldn't process that request.</span>
          <span className="state-desc">
            {entry.error instanceof ApiError ? entry.error.message : 'Unexpected error. Please try again.'}
          </span>
        </div>
      </div>
    )
  }

  const r = entry.response
  const meta = ANSWER_TYPE_META[r.answer_type] || ANSWER_TYPE_META.unsupported
  const isUnsupported = r.answer_type === 'unsupported'

  return (
    <div className="ask-hri-message ask-hri-message-assistant">
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
        <span className={`badge ${meta.className}`}>
          {isUnsupported && <IconInfo size={12} style={{ marginRight: 4 }} />}
          {meta.label}
        </span>
        {r.project_id && <span className="muted" style={{ fontSize: 11 }}>{r.project_id}{r.reporting_month ? ` · ${r.reporting_month}` : ''}</span>}
      </div>

      <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{r.message}</p>

      {r.predictions && <PredictionSummary predictions={r.predictions} isActual={r.answer_type === 'actual'} />}

      {r.citations && r.citations.length > 0 && (
        <div className="stack" style={{ gap: 6, marginTop: 10 }}>
          {r.citations.map((c, idx) => (
            <div key={idx} className="evidence-card">
              <div className="evidence-meta">
                <span className="evidence-citation">{c.citation}</span>
              </div>
              <p className="evidence-text">{c.text}</p>
            </div>
          ))}
        </div>
      )}

      {r.disclaimer && (
        <DisclaimerBox warn={r.answer_type === 'hypothetical'}>{r.disclaimer}</DisclaimerBox>
      )}
    </div>
  )
}

function PredictionSummary({ predictions, isActual }) {
  const items = isActual
    ? [
        predictions.actual_significant_delay != null && `Significant delay: ${predictions.actual_significant_delay ? 'Yes' : 'No'}`,
        predictions.actual_final_delay_days != null && `Final delay: ${formatDays(predictions.actual_final_delay_days)}`,
        predictions.actual_cost_overrun != null && `Cost overrun: ${predictions.actual_cost_overrun ? 'Yes' : 'No'}`,
        predictions.actual_final_cost_overrun_pct != null && `Final cost overrun: ${formatPercent(predictions.actual_final_cost_overrun_pct)}`,
      ].filter(Boolean)
    : [
        predictions.significant_delay_probability != null && `Significant-delay probability: ${formatPercent(predictions.significant_delay_probability * 100)}`,
        predictions.final_delay_days_predicted != null && `Predicted final delay: ${formatDays(predictions.final_delay_days_predicted)}`,
        predictions.cost_overrun_probability != null && `Cost-overrun probability: ${formatPercent(predictions.cost_overrun_probability * 100)}`,
        predictions.final_cost_overrun_pct_predicted != null && `Predicted final cost overrun: ${formatPercent(predictions.final_cost_overrun_pct_predicted)}`,
      ].filter(Boolean)

  if (items.length === 0) return null
  return (
    <div className="grid two-col-grid" style={{ marginTop: 8, gap: 4 }}>
      {items.map((text) => (
        <div key={text} className="muted" style={{ fontSize: 12.5 }}>
          {text}
        </div>
      ))}
    </div>
  )
}
