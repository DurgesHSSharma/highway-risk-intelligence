import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Topbar from './Topbar'

export default function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className="app-shell">
      <Sidebar open={menuOpen} onNavigate={() => setMenuOpen(false)} />
      {menuOpen && <div className="sidebar-backdrop open" onClick={() => setMenuOpen(false)} />}
      <div className="app-main">
        <Topbar onMenuClick={() => setMenuOpen((v) => !v)} />
        <main className="page">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
