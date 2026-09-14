// Small hand-authored inline SVG icon set (no icon library / external
// service dependency, per the zero-cost constraint). Each icon is a plain
// stroke-based line glyph that inherits color via currentColor.

const base = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

function Svg({ size = 18, children, ...rest }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} {...rest} aria-hidden="true" focusable="false">
      {children}
    </svg>
  )
}

export function IconDashboard(props) {
  return (
    <Svg {...props}>
      <rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="13" y="3.5" width="7.5" height="4.5" rx="1.5" />
      <rect x="13" y="10.5" width="7.5" height="10" rx="1.5" />
      <rect x="3.5" y="13.5" width="7.5" height="7" rx="1.5" />
    </Svg>
  )
}

export function IconProjects(props) {
  return (
    <Svg {...props}>
      <path d="M3.5 6.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />
    </Svg>
  )
}

export function IconRisk(props) {
  return (
    <Svg {...props}>
      <path d="M12 3.5 3 20h18z" />
      <path d="M12 9.5v4.5" />
      <circle cx="12" cy="17" r="0.9" fill="currentColor" stroke="none" />
    </Svg>
  )
}

export function IconSimulator(props) {
  return (
    <Svg {...props}>
      <path d="M4 18V9l5-3 5 3v9" />
      <path d="M14 18v-5l5-2.5v7.5" />
      <path d="M2.5 18h19" />
    </Svg>
  )
}

export function IconSearch(props) {
  return (
    <Svg {...props}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m20 20-4.3-4.3" />
    </Svg>
  )
}

export function IconInconsistency(props) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5v5.5" />
      <circle cx="12" cy="16.3" r="0.9" fill="currentColor" stroke="none" />
    </Svg>
  )
}

export function IconAnalytics(props) {
  return (
    <Svg {...props}>
      <path d="M4 20V10" />
      <path d="M11 20V4" />
      <path d="M18 20v-7" />
      <path d="M2.5 20h19" />
    </Svg>
  )
}

export function IconReports(props) {
  return (
    <Svg {...props}>
      <path d="M6 3.5h9l4 4V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1z" />
      <path d="M14.5 3.5V8h4" />
      <path d="M8.5 12.5h7M8.5 15.5h7M8.5 18h4" />
    </Svg>
  )
}

export function IconMenu(props) {
  return (
    <Svg {...props}>
      <path d="M3.5 6.5h17M3.5 12h17M3.5 17.5h17" />
    </Svg>
  )
}

export function IconAlertTriangle(props) {
  return (
    <Svg {...props}>
      <path d="M12 4 2.5 20h19z" />
      <path d="M12 9.5v4.5" />
      <circle cx="12" cy="17" r="0.9" fill="currentColor" stroke="none" />
    </Svg>
  )
}

export function IconInfo(props) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5.5" />
      <circle cx="12" cy="8" r="0.9" fill="currentColor" stroke="none" />
    </Svg>
  )
}

export function IconCheckCircle(props) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12.5 2.5 2.5 5.5-6" />
    </Svg>
  )
}

export function IconExternalLink(props) {
  return (
    <Svg {...props}>
      <path d="M9 6H5.5A1.5 1.5 0 0 0 4 7.5v11A1.5 1.5 0 0 0 5.5 20h11a1.5 1.5 0 0 0 1.5-1.5V15" />
      <path d="M14 4h6v6" />
      <path d="M20 4 11 13" />
    </Svg>
  )
}

export function IconEye(props) {
  return (
    <Svg {...props}>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="2.6" />
    </Svg>
  )
}

export function IconChevronRight(props) {
  return (
    <Svg {...props}>
      <path d="m9 5 7 7-7 7" />
    </Svg>
  )
}

export function IconRefresh(props) {
  return (
    <Svg {...props}>
      <path d="M20 11A8 8 0 1 0 18.5 16" />
      <path d="M20 5v6h-6" />
    </Svg>
  )
}

export function IconArrowUp(props) {
  return (
    <Svg {...props}>
      <path d="M12 19V5" />
      <path d="m6 11 6-6 6 6" />
    </Svg>
  )
}

export function IconArrowDown(props) {
  return (
    <Svg {...props}>
      <path d="M12 5v14" />
      <path d="m6 13 6 6 6-6" />
    </Svg>
  )
}

export function IconX(props) {
  return (
    <Svg {...props}>
      <path d="m5 5 14 14M19 5 5 19" />
    </Svg>
  )
}

export function IconPrint(props) {
  return (
    <Svg {...props}>
      <path d="M6.5 8.5V4h11v4.5" />
      <rect x="4" y="8.5" width="16" height="7" rx="1.2" />
      <path d="M6.5 15h11V20h-11z" />
    </Svg>
  )
}

export function IconRoad(props) {
  return (
    <Svg {...props}>
      <path d="M8.5 4 4.5 20" />
      <path d="M15.5 4l4 16" />
      <path d="M12 4v3M12 10v3M12 16v3" />
    </Svg>
  )
}
