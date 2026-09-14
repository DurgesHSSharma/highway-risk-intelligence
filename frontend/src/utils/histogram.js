/** Buckets numeric values into fixed-width bins for a histogram chart. */
export function buildHistogram(values, binWidth, unitLabel = '') {
  const clean = values.filter((v) => v != null && !Number.isNaN(v))
  if (clean.length === 0) return []
  const max = Math.max(...clean)
  const binCount = Math.max(1, Math.ceil((max + 1) / binWidth))
  const bins = Array.from({ length: binCount }, (_, i) => ({
    name: `${i * binWidth}-${(i + 1) * binWidth}${unitLabel}`,
    value: 0,
  }))
  clean.forEach((v) => {
    const idx = Math.min(binCount - 1, Math.floor(v / binWidth))
    bins[idx].value += 1
  })
  return bins.filter((b) => b.value > 0)
}
