export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return Number(value).toLocaleString('en-IN', { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${formatNumber(value, digits)}%`
}

export function formatCrore(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `₹${formatNumber(value, digits)} Cr`
}

export function formatDays(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const n = Number(value)
  return `${formatNumber(n, 0)} day${Math.abs(n) === 1 ? '' : 's'}`
}

export function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return value
  }
}

export function formatMonthLabel(reportingMonth) {
  if (!reportingMonth) return '—'
  const [year, month] = reportingMonth.split('-')
  const date = new Date(Number(year), Number(month) - 1, 1)
  return date.toLocaleDateString('en-IN', { year: 'numeric', month: 'long' })
}

export function titleCase(value) {
  if (!value) return value
  return String(value)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}
