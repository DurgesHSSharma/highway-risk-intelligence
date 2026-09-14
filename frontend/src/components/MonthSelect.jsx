import { formatMonthLabel } from '../utils/format'

export default function MonthSelect({ snapshots, value, onChange, id = 'reporting-month' }) {
  return (
    <div className="field">
      <label htmlFor={id}>Reporting month</label>
      <select id={id} className="select" value={value || ''} onChange={(e) => onChange(e.target.value)}>
        {snapshots.map((s) => (
          <option key={s.reporting_month} value={s.reporting_month}>
            {formatMonthLabel(s.reporting_month)}
            {s.is_terminal_snapshot ? ' (final / terminal)' : ''}
          </option>
        ))}
      </select>
    </div>
  )
}
