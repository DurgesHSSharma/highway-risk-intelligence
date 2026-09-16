import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { PALETTE } from '../../utils/palette'

// A small-sample point is drawn hollow/muted instead of the series color, so
// a year with only 1-4 scored projects doesn't visually read as trustworthy
// as one with dozens -- the same "never let a small sample look like a solid
// signal" rule the Segment Analytics table already enforces with its badge.
function SampleAwareDot({ cx, cy, payload, color }) {
  if (payload?.small_sample) {
    return <circle cx={cx} cy={cy} r={3.5} fill="#fff" stroke={PALETTE.slate} strokeWidth={1.5} />
  }
  return <circle cx={cx} cy={cy} r={3} fill={color} stroke={color} />
}

/**
 * Single-series trend line over `period` (a year string). Historical and
 * predicted trends are ALWAYS rendered as separate chart instances with
 * separate data arrays -- never combined into one series -- per the
 * historical/predicted separation rule.
 */
export default function TrendLineChart({ data, dataKey, color = PALETTE.blue, yFormatter, height = 220 }) {
  const hasSmallSample = data?.some((point) => point?.small_sample)
  return (
    <>
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
          <Line
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={2}
            dot={(props) => <SampleAwareDot key={props.payload?.period} {...props} color={color} />}
          />
        </LineChart>
      </ResponsiveContainer>
      {hasSmallSample && (
        <p className="muted" style={{ fontSize: 11, marginTop: 4 }}>
          Hollow points mark years with a small scored-project sample (fewer than ~8); treat those years with caution.
        </p>
      )}
    </>
  )
}
