import { useEffect, useState, type FormEvent } from 'react'
import { ApiError, staffApi, type CreateStaffInput } from '../api/client'
import { useAuth, type Role, type User } from '../store/auth'
import EditStaffModal from '../components/EditStaffModal'

const ROLES: Role[] = ['admin', 'manager', 'agent']

const EMPTY_FORM: CreateStaffInput = {
  email: '',
  password: '',
  full_name: '',
  role: 'agent',
}

export default function Staff() {
  const currentUser = useAuth((s) => s.user)!
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState<CreateStaffInput>(EMPTY_FORM)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [editFor, setEditFor] = useState<User | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      setUsers(await staffApi.list())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load staff')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const onCreate = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await staffApi.create({ ...form, full_name: form.full_name || null })
      setForm(EMPTY_FORM)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create user')
    } finally {
      setSubmitting(false)
    }
  }

  const onDeactivate = async (u: User) => {
    setError(null)
    try {
      await staffApi.deactivate(u.id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to deactivate user')
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Staff</h1>
      <p className="page-subtitle">Create staff accounts and manage roles.</p>

      {error && <p className="form-error">{error}</p>}

      <section className="card">
        <div className="card-head">Add staff member</div>
        <form className="form-row" onSubmit={onCreate}>
          <input
            type="email"
            placeholder="Email"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <input
            type="text"
            placeholder="Full name (optional)"
            value={form.full_name ?? ''}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          />
          <input
            type="password"
            placeholder="Password (min 8)"
            required
            minLength={8}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <select
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? 'Adding…' : 'Add'}
          </button>
        </form>
      </section>

      <section className="card">
        <div className="card-head">All staff</div>
        {loading ? (
          <p className="hint">Loading…</p>
        ) : (
          <div className="table-wrap">
            <table className="table staff-table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th className="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.email}</td>
                    <td>{u.full_name || '—'}</td>
                    <td>
                      <span className={`role-badge role-${u.role}`}>{u.role}</span>
                    </td>
                    <td>
                      <span className={`badge ${u.is_active ? 'badge--ok' : 'badge--err'}`}>
                        {u.is_active ? 'active' : 'inactive'}
                      </span>
                    </td>
                    <td className="col-actions">
                      <div className="quick-actions">
                        <button className="icon-btn" title="Edit" onClick={() => setEditFor(u)}>
                          ✏️
                        </button>
                        {u.is_active && u.id !== currentUser.id && (
                          <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => onDeactivate(u)}
                          >
                            Deactivate
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {editFor && (
        <EditStaffModal
          staff={editFor}
          isSelf={editFor.id === currentUser.id}
          onClose={() => setEditFor(null)}
          onSaved={() => {
            setEditFor(null)
            void load()
          }}
        />
      )}
    </div>
  )
}
