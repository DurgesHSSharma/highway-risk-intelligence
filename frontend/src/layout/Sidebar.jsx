import { Link, useLocation } from 'react-router-dom'
import Logo from '../components/Logo'
import {
  IconAnalytics,
  IconChat,
  IconDashboard,
  IconEye,
  IconInconsistency,
  IconProjects,
  IconReports,
  IconRisk,
  IconSearch,
  IconSimulator,
} from '../components/icons'

// /projects/:id/risk-summary, /projects/:id/decision-intelligence, and
// /projects/:id/simulator all share the "/projects" prefix with the plain
// Projects section, so NavLink's default prefix matching would highlight
// "Projects" for those nested routes too. Each item gets an explicit
// isActive test instead.
const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: IconDashboard, isActive: (p) => p === '/' },
  {
    to: '/projects',
    label: 'Projects',
    icon: IconProjects,
    isActive: (p) =>
      p === '/projects' ||
      (p.startsWith('/projects/') && !p.includes('/risk-summary') && !p.includes('/simulator') && !p.includes('/decision-intelligence')),
  },
  { to: '/risk-summary', label: 'AI Risk Summary', icon: IconRisk, isActive: (p) => p.includes('risk-summary') },
  {
    to: '/decision-intelligence',
    label: 'Decision Intelligence',
    icon: IconEye,
    isActive: (p) => p.includes('decision-intelligence'),
  },
  { to: '/simulator', label: 'What-if Simulator', icon: IconSimulator, isActive: (p) => p.includes('simulator') },
  { to: '/documents', label: 'Document Search', icon: IconSearch, isActive: (p) => p === '/documents' },
  { to: '/inconsistencies', label: 'Inconsistencies', icon: IconInconsistency, isActive: (p) => p === '/inconsistencies' },
  { to: '/analytics', label: 'Analytics', icon: IconAnalytics, isActive: (p) => p === '/analytics' },
  { to: '/reports', label: 'Reports', icon: IconReports, isActive: (p) => p === '/reports' || p.startsWith('/reports/') },
  { to: '/ask', label: 'Ask HRI', icon: IconChat, isActive: (p) => p === '/ask' },
]

export default function Sidebar({ open, onNavigate }) {
  const location = useLocation()

  return (
    <aside className={`sidebar${open ? ' open' : ''}`} aria-label="Primary navigation">
      <Logo variant="full" />
      <nav className="sidebar-nav">
        {NAV_ITEMS.map(({ to, label, icon: Icon, isActive }) => {
          const active = isActive(location.pathname)
          return (
            <Link
              key={to}
              to={to}
              className={`sidebar-link${active ? ' active' : ''}`}
              aria-current={active ? 'page' : undefined}
              onClick={onNavigate}
            >
              <Icon size={17} />
              {label}
            </Link>
          )
        })}
      </nav>
      <div className="sidebar-footer">
        <strong>HRI</strong>
        Highway Risk Intelligence
        <div className="sidebar-tagline">PREDICT DELAYS • CONTROL COSTS</div>
      </div>
    </aside>
  )
}
