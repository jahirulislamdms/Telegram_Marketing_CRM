import { useState } from 'react'
import { ApiError, meApi } from '../api/client'
import { useAuth } from '../store/auth'

/** My Profile (§15.4 #3): edit full name + email; role/status/created are read-only. */
export default function ProfileModal({ onClose }: { onClose: () => void }) {
  const user = useAuth((s) => s.user)!
  const setUser = useAuth((s) => s.setUser)
  const [fullName, setFullName] = useState(user.full_name ?? '')
  const [email, setEmail] = useState(user.email)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const save = async () => {
    setError(null)
    setSuccess(null)
    if (!fullName.trim()) {
      setError('Name cannot be empty.')
      return
    }
    setBusy(true)
    try {
      const updated = await meApi.update({ full_name: fullName.trim(), email: email.trim() })
      setUser(updated)
      setSuccess('Profile updated successfully.')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to save profile')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>My profile</h2>
          <button className="icon-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {error && <p className="form-error">{error}</p>}
        {success && <p className="form-success">{success}</p>}

        <div className="field-block">
          <span className="label">Full name</span>
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Full name" />
        </div>
        <div className="field-block">
          <span className="label">Email address</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
        </div>

        <div className="readonly-grid">
          <div>
            <span className="label">Role</span>
            <span className={`role-badge role-${user.role}`}>{user.role}</span>
          </div>
          <div>
            <span className="label">Account status</span>
            <span className={`badge ${user.is_active ? 'badge--ok' : 'badge--err'}`}>
              {user.is_active ? 'active' : 'inactive'}
            </span>
          </div>
          <div>
            <span className="label">Created</span>
            <span className="readonly-value">{new Date(user.created_at).toLocaleDateString()}</span>
          </div>
        </div>

        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Close
          </button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>
            {busy ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  )
}
