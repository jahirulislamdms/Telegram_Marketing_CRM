import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { meApi } from '../api/client'
import { applyTheme } from '../lib/theme'
import { useAuth, type Role } from '../store/auth'

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
  { to: '/staff', label: 'Staff', icon: '☰', end: false, roles: ['admin'] },
]

export default function AppLayout() {
  const user = useAuth((s) => s.user)!
  const logout = useAuth((s) => s.logout)
  const setUser = useAuth((s) => s.setUser)
  const navigate = useNavigate()

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

  const initials = (user.full_name || user.email).slice(0, 2).toUpperCase()

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
        <header className="topbar">
          <div className="topbar-title">Telegram Marketing CRM</div>
          <div className="topbar-actions">
            <button className="icon-btn" onClick={toggleTheme} title="Toggle theme">
              {user.theme === 'dark' ? '☀' : '☾'}
            </button>
            <div className="user-chip">
              <span className="avatar">{initials}</span>
              <span className="user-meta">
                <span className="user-name">{user.full_name || user.email}</span>
                <span className={`role-badge role-${user.role}`}>{user.role}</span>
              </span>
            </div>
            <button className="btn btn-ghost" onClick={handleLogout}>
              Log out
            </button>
          </div>
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
