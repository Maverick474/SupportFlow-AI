import { useState } from 'react'

import { useSupportFlow } from '../context/contextApi.jsx'

export default function Header({ onNavigate, onToggleSidebar, publicView = false }) {
  const { user, logout, backendOnline } = useSupportFlow()
  const [menuOpen, setMenuOpen] = useState(false)

  async function handleLogout() {
    setMenuOpen(false)
    await logout()
    onNavigate?.('/login')
  }

  return (
    <header className={publicView ? 'site-header public-header' : 'site-header app-header'}>
      <div className="header-start">
        {!publicView && (
          <button
            className="icon-button mobile-menu-button"
            type="button"
            onClick={onToggleSidebar}
            aria-label="Open conversation sidebar"
          >
            <span aria-hidden="true">☰</span>
          </button>
        )}
        <button className="brand" type="button" onClick={() => onNavigate?.(user ? '/app' : '/login')}>
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span className="brand-name">SupportFlow</span>
          <span className="brand-badge">AI</span>
        </button>
      </div>

      {publicView ? (
        <div className="public-header-note">
          <span className="status-dot online" />
          Grounded support, every time
        </div>
      ) : (
        <div className="header-actions">
          <div className="connection-pill" title="FastAPI connection status">
            <span className={`status-dot ${backendOnline ? 'online' : backendOnline === false ? 'offline' : ''}`} />
            <span>{backendOnline ? 'Systems ready' : backendOnline === false ? 'Server offline' : 'Checking server'}</span>
          </div>
          <div className="profile-menu">
            <button
              type="button"
              className="profile-button"
              onClick={() => setMenuOpen((current) => !current)}
              aria-expanded={menuOpen}
            >
              <span className="avatar">{user?.full_name?.charAt(0)?.toUpperCase() || 'U'}</span>
              <span className="profile-copy">
                <strong>{user?.full_name || 'Support user'}</strong>
                <small>{user?.role || 'customer'}</small>
              </span>
              <span aria-hidden="true">⌄</span>
            </button>
            {menuOpen && (
              <div className="profile-popover">
                <p>{user?.email}</p>
                <button type="button" onClick={handleLogout}>Sign out</button>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  )
}
