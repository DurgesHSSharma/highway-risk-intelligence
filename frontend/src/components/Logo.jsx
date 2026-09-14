// Local, dependency-free HRI logo mark: a rounded badge combining a
// highway curve with an ascending analytics bar, plus the wordmark. No
// external image URL / logo service is used (zero-cost, local SVG only).

export function LogoMark({ size = 34 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="hriMarkGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#2563eb" />
          <stop offset="100%" stopColor="#0f2142" />
        </linearGradient>
      </defs>
      <rect x="0.5" y="0.5" width="39" height="39" rx="10" fill="url(#hriMarkGrad)" />
      <path
        d="M7 27.5C11 27.5 12.5 16 17 16c3.2 0 3.6 6 6.8 6 2.4 0 3-3.3 5.2-3.3"
        fill="none"
        stroke="#bfd4ff"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path d="M22 27.5h4l2.2-6 2.3 6H33" fill="none" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="7" y="10.5" width="2.2" height="6" rx="1.1" fill="#7fa8ff" />
      <rect x="11" y="7.5" width="2.2" height="9" rx="1.1" fill="#a9c4ff" />
      <rect x="15" y="9.5" width="2.2" height="7" rx="1.1" fill="#dbe6ff" />
    </svg>
  )
}

export default function Logo({ variant = 'full', size = 34 }) {
  if (variant === 'mark') return <LogoMark size={size} />

  return (
    <div className="sidebar-brand">
      <LogoMark size={size} />
      <div className="sidebar-brand-text">
        <span className="sidebar-brand-name">HRI</span>
        <span className="sidebar-brand-sub">Highway Risk Intelligence</span>
      </div>
    </div>
  )
}
