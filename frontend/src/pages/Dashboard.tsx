import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../store/auth'

interface Health {
  status: string
  service: string
  version: string
  environment: string
}

export default function Dashboard() {
  const user = useAuth((s) => s.user)!
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch('/health')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: Health) => !cancelled && setHealth(data))
      .catch(() => !cancelled && setHealthError(true))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="page">
      <h1 className="page-title">Dashboard</h1>
      <p className="page-subtitle">
        Welcome back, {user.full_name || user.email}. You are signed in as{' '}
        <span className={`role-badge role-${user.role}`}>{user.role}</span>.
      </p>

      <div className="card-grid">
        <section className="card">
          <div className="card-head">Backend health</div>
          {health && (
            <>
              <div className="stat">
                <span className="stat-value">Online</span>
                <span className="badge badge--ok">200</span>
              </div>
              <dl className="meta">
                <div>
                  <dt>Service</dt>
                  <dd>{health.service}</dd>
                </div>
                <div>
                  <dt>Version</dt>
                  <dd>{health.version}</dd>
                </div>
                <div>
                  <dt>Environment</dt>
                  <dd>{health.environment}</dd>
                </div>
              </dl>
            </>
          )}
          {healthError && <p className="hint">API unreachable.</p>}
          {!health && !healthError && <p className="hint">Checking…</p>}
        </section>

        <section className="card">
          <div className="card-head">Your account</div>
          <dl className="meta">
            <div>
              <dt>Email</dt>
              <dd>{user.email}</dd>
            </div>
            <div>
              <dt>Role</dt>
              <dd>{user.role}</dd>
            </div>
            <div>
              <dt>Theme</dt>
              <dd>{user.theme}</dd>
            </div>
          </dl>
        </section>

        {user.role === 'admin' && (
          <section className="card">
            <div className="card-head">Administration</div>
            <p className="hint">Manage staff accounts, roles, and the audit log.</p>
            <Link className="btn btn-primary" to="/staff">
              Open Staff
            </Link>
          </section>
        )}
      </div>
    </div>
  )
}
