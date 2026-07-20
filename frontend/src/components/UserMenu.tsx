import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../store/auth'
import ProfileModal from './ProfileModal'
import ChangePasswordModal from './ChangePasswordModal'

/** Clickable logged-in-user chip → dropdown (My Profile / Change Password / Log out). */
export default function UserMenu({ onLogout }: { onLogout: () => void }) {
  const user = useAuth((s) => s.user)!
  const [open, setOpen] = useState(false)
  const [showProfile, setShowProfile] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const initials = (user.full_name || user.email).slice(0, 2).toUpperCase()

  return (
    <div className="user-menu" ref={ref}>
      <button
        className="user-chip user-chip--btn"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="avatar">{initials}</span>
        <span className="user-meta">
          <span className="user-name">{user.full_name || user.email}</span>
          <span className={`role-badge role-${user.role}`}>{user.role}</span>
        </span>
        <span className="chip-caret">▾</span>
      </button>

      {open && (
        <div className="user-dropdown" role="menu">
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false)
              setShowProfile(true)
            }}
          >
            My Profile
          </button>
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false)
              setShowPassword(true)
            }}
          >
            Change Password
          </button>
          <div className="user-dropdown-sep" />
          <button role="menuitem" className="user-dropdown-danger" onClick={onLogout}>
            Log out
          </button>
        </div>
      )}

      {showProfile && <ProfileModal onClose={() => setShowProfile(false)} />}
      {showPassword && <ChangePasswordModal onClose={() => setShowPassword(false)} />}
    </div>
  )
}
