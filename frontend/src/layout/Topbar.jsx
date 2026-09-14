import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { IconMenu, IconSearch } from '../components/icons'

export default function Topbar({ onMenuClick }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    const value = query.trim()
    if (!value) return
    navigate(`/projects?q=${encodeURIComponent(value)}`)
  }

  return (
    <header className="app-topbar">
      <button type="button" className="topbar-menu-btn" onClick={onMenuClick} aria-label="Toggle navigation menu">
        <IconMenu size={19} />
      </button>
      <span className="topbar-title">Highway Risk Intelligence</span>
      <span className="topbar-spacer" />
      <form className="topbar-search" onSubmit={handleSubmit} role="search">
        <IconSearch size={15} />
        <input
          type="search"
          placeholder="Search projects (e.g. HRI-0006)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search projects"
        />
      </form>
    </header>
  )
}
