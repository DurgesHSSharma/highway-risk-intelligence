import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { PALETTE } from '../../utils/palette'

/**
 * Single-series trend line over `period` (a year string). Historical and
 * predicted trends are ALWAYS rendered as separate chart instances with
 * separate data arrays -- never combined into one series -- per the
 * historical/predicted separation rule.
 */
export default function TrendLineChart({ data, dataKey, color = PALETTE.blue, yFormatter, height = 220 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 20, bottom: 4, left: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="period" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={yFormatter} />
        <Tooltip
          formatter={(value) => (yFormatter ? yFormatter(value) : value)}
          labelFormatter={(label, payload) => {
            const point = payload?.[0]?.payload
            return point?.small_sample ? `${label} (small sample, n=${point.project_count ?? point.scored_project_count})` : label
          }}
        />
        <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  )
}
