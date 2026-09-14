export default function KpiCard({ icon, tone = 'blue', label, value, note }) {
  return (
    <div className="kpi-card">
      <div className="kpi-top">
        <span className={`kpi-icon tone-${tone}`}>{icon}</span>
        <span className="kpi-label">{label}</span>
      </div>
      <div className="kpi-value">{value}</div>
      {note && <div className="kpi-note">{note}</div>}
    </div>
  )
}
