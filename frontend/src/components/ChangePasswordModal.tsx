import { useState } from 'react'
import { ApiError, meApi } from '../api/client'

/** Change Password (§15.4 #4): verifies the current password server-side; the
 * user is NOT logged out on success. */
export default function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setError(null)
    setSuccess(null)
    if (next.length < 8) {
      setError('New password must be at least 8 characters.')
      return
    }
    if (next !== confirm) {
      setError('New password and confirmation do not match.')
      return
    }
    setBusy(true)
    try {
      await meApi.changePassword({ current_password: current, new_password: next })
      setSuccess('Password changed successfully.')
      setCurrent('')
      setNext('')
      setConfirm('')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to change password')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Change password</h2>
          <button className="icon-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {error && <p className="form-error">{error}</p>}
        {success && <p className="form-success">{success}</p>}

        <div className="field-block">
          <span className="label">Current password</span>
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" />
        </div>
        <div className="field-block">
          <span className="label">New password</span>
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" placeholder="At least 8 characters" />
        </div>
        <div className="field-block">
          <span className="label">Confirm new password</span>
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
        </div>

        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Close
          </button>
          <button
            className="btn btn-primary"
            onClick={submit}
            disabled={busy || !current || !next || !confirm}
          >
            {busy ? 'Updating…' : 'Update password'}
          </button>
        </div>
      </div>
    </div>
  )
}
