import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { meApi } from '../api/client'
import { applyTheme } from '../lib/theme'
import { useAuth, type Role } from '../store/auth'
import UserMenu from './UserMenu'

interface NavItem {
  to: string
  label: string
  icon: string
  end: boolean
  roles?: Role[]
}

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: '▤', end: true },
  { to: '/accounts', label: 'Accounts', icon: '⊚', end: false, roles: ['admin', 'manager'] },
  { to: '/warmup', label: 'Warmup', icon: '♨', end: false, roles: ['admin', 'manager'] },
  { to: '/contacts', label: 'Contacts', icon: '☺', end: false },
  { to: '/pipeline', label: 'Pipeline', icon: '▦', end: false },
  { to: '/inbox', label: 'Inbox', icon: '✉', end: false },
  { to: '/groups', label: 'Groups', icon: '⧉', end: false, roles: ['admin', 'manager'] },
  { to: '/sender', label: 'Sender', icon: '➤', end: false, roles: ['admin', 'manager'] },
  { to: '/campaigns', label: 'Campaigns', icon: '◆', end: false, roles: ['admin', 'manager'] },
  { to: '/bots', label: 'Bots', icon: '⌬', end: false, roles: ['admin', 'manager'] },
  { to: '/analytics', label: 'Analytics', icon: '◷', end: false, roles: ['admin', 'manager'] },
  { to: '/settings', label: 'Settings', icon: '⚙', end: false, roles: ['admin'] },
  { to: '/staff', label: 'Staff', icon: '☰', end: false, roles: ['admin'] },
]

export default function AppLayout() {
  const user = useAuth((s) => s.user)!
  const logout = useAuth((s) => s.logout)
  const setUser = useAuth((s) => s.setUser)
  const navigate = useNavigate()
  const [scrolled, setScrolled] = useState(false)
  const contentRef = useRef<HTMLElement>(null)

  // Depending on page height either the window or the .content pane is the
  // scroll container, so the sticky top bar's shadow watches both.
  const updateScrolled = useCallback(() => {
    const pane = contentRef.current
    setScrolled(window.scrollY > 4 || (pane ? pane.scrollTop > 4 : false))
  }, [])

  useEffect(() => {
    window.addEventListener('scroll', updateScrolled, { passive: true })
    return () => window.removeEventListener('scroll', updateScrolled)
  }, [updateScrolled])

  const toggleTheme = async () => {
    const next = user.theme === 'dark' ? 'light' : 'dark'
    applyTheme(next) // optimistic
    try {
      const updated = await meApi.update({ theme: next })
      setUser(updated)
    } catch {
      applyTheme(user.theme) // revert on failure
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand" title="Telegram Marketing CRM">TG</div>
        <nav>
          {NAV.filter((i) => !i.roles || i.roles.includes(user.role)).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-item${isActive ? ' nav-item--active' : ''}`}
              title={item.label}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="main">
        <header className={`topbar${scrolled ? ' topbar--scrolled' : ''}`}>
          <div className="topbar-title">Telegram Marketing CRM</div>
          <div className="topbar-actions">
            <button className="icon-btn" onClick={toggleTheme} title="Toggle theme">
              {user.theme === 'dark' ? '☀' : '☾'}
            </button>
            <UserMenu onLogout={handleLogout} />
          </div>
        </header>

        <main className="content" ref={contentRef} onScroll={updateScrolled}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
