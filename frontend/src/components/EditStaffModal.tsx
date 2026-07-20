import { useState } from 'react'
import { ApiError, staffApi, type UpdateStaffInput } from '../api/client'
import type { Role, User } from '../store/auth'

const ROLES: Role[] = ['admin', 'manager', 'agent']

/** Edit Staff Member (§15.4 #6): name/email/role/status + optional password
 * (blank = keep current). Email unique, name required, password ≥8 if provided. */
export default function EditStaffModal({
  staff,
  isSelf,
  onClose,
  onSaved,
}: {
  staff: User
  isSelf: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const [fullName, setFullName] = useState(staff.full_name ?? '')
  const [email, setEmail] = useState(staff.email)
  const [role, setRole] = useState<Role>(staff.role)
  const [isActive, setIsActive] = useState(staff.is_active)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const save = async () => {
    setError(null)
    setSuccess(null)
    if (!fullName.trim()) {
      setError('Name is required.')
      return
    }
    if (password && password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    const payload: UpdateStaffInput = {
      full_name: fullName.trim(),
      email: email.trim(),
      role,
      is_active: isActive,
    }
    if (password) payload.password = password // blank → keep existing
    setBusy(true)
    try {
      await staffApi.update(staff.id, payload)
      setSuccess('Staff member updated successfully.')
      onSaved()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to update staff member')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Edit staff member</h2>
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
          <span className="label">Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
        </div>
        <div className="edit-grid">
          <div className="field-block">
            <span className="label">Role</span>
            <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <div className="field-block">
            <span className="label">Status</span>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={isActive}
                disabled={isSelf}
                onChange={(e) => setIsActive(e.target.checked)}
              />
              <span>{isActive ? 'Active' : 'Inactive'}{isSelf ? ' (you)' : ''}</span>
            </label>
          </div>
        </div>
        <div className="field-block">
          <span className="label">New password (optional)</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            placeholder="Leave blank to keep current"
          />
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
