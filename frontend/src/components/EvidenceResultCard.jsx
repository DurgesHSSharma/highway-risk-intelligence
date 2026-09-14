export default function EvidenceResultCard({ result }) {
  return (
    <div className="evidence-card">
      <div className="evidence-meta">
        <span className="evidence-citation">{result.citation}</span>
        <span className="badge badge-info">rank {result.rank}</span>
        <span className="badge badge-neutral">similarity {result.similarity_score.toFixed(2)}</span>
        <span className="badge badge-neutral">{result.extraction_method}</span>
        {result.quality_flag && <span className="badge badge-medium">{result.quality_flag.replace(/_/g, ' ')}</span>}
      </div>
      {result.section_heading && <div className="muted" style={{ fontSize: 11.5 }}>{result.section_heading}</div>}
      <p className="evidence-text">{result.text}</p>
      <div className="muted" style={{ fontSize: 11 }}>{result.source_filename} · p.{result.page_number}</div>
    </div>
  )
}
