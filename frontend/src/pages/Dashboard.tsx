import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { analyticsApi, type DashboardSnapshot, type InboxEvent } from '../api/client'
import { useInboxSocket } from '../lib/useInboxSocket'
import { useAuth } from '../store/auth'

const ACCOUNT_TILES: Array<{ key: string; label: string; tone: string }> = [
  { key: 'active', label: 'Active', tone: 'ok' },
  { key: 'warming', label: 'Warming', tone: 'wait' },
  { key: 'quarantined', label: 'Quarantined', tone: 'err' },
  { key: 'banned', label: 'Banned', tone: 'err' },
  { key: 'logged_out', label: 'Logged out', tone: 'muted' },
]

function timeAgo(iso: string | null): string {
  if (!iso) return '—'
  const secs = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  return `${Math.floor(secs / 3600)}h ago`
}

export default function Dashboard() {
  const user = useAuth((s) => s.user)!
  const isManager = user.role === 'admin' || user.role === 'manager'

  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null)
  const [error, setError] = useState(false)
  const [live, setLive] = useState(false)
  const inFlight = useRef(false)

  const refresh = useCallback(async () => {
    if (!isManager || inFlight.current) return
    inFlight.current = true
    try {
      setSnapshot(await analyticsApi.dashboard())
      setError(false)
    } catch {
      setError(true)
    } finally {
      inFlight.current = false
    }
  }, [isManager])

  useEffect(() => {
    if (!isManager) return
    refresh()
    const id = setInterval(refresh, 15000)
    return () => clearInterval(id)
  }, [isManager, refresh])

  // Live push: a `dashboard` event carries a fresh snapshot; other inbox events
  // (a message landing, a bot reply) trigger a re-fetch so counters stay current.
  const onEvent = useCallback(
    (e: InboxEvent) => {
      if (e.type === 'dashboard' && e.snapshot) {
        setSnapshot(e.snapshot)
        setLive(true)
      } else if (e.type === 'message' || e.type === 'bot_message') {
        refresh()
      }
    },
    [refresh],
  )
  useInboxSocket(onEvent)

  if (!isManager) {
    return (
      <div className="page">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">
          Welcome back, {user.full_name || user.email}. You are signed in as{' '}
          <span className={`role-badge role-${user.role}`}>{user.role}</span>.
        </p>
        <div className="card-grid">
          <section className="card">
            <div className="card-head">Your workspace</div>
            <p className="hint">Head to your Inbox and Contacts to pick up conversations.</p>
            <Link className="btn btn-primary" to="/inbox">
              Open Inbox
            </Link>
          </section>
        </div>
      </div>
    )
  }

  const acc = snapshot?.accounts ?? {}
  const caps = snapshot?.caps
  const proxies = snapshot?.proxies ?? {}

  return (
    <div className="page">
      <div className="dash-head">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">
            Live system monitoring
            {snapshot && (
              <span className="hint-inline"> · updated {timeAgo(snapshot.generated_at)}</span>
            )}
          </p>
        </div>
        <div className="dash-head-actions">
          <span className={`live-dot ${live ? 'live-dot--on' : ''}`} title={live ? 'Receiving live updates' : 'Polling'}>
            ● {live ? 'Live' : 'Polling'}
          </span>
          <button className="btn btn-ghost btn-sm" onClick={refresh}>
            Refresh
          </button>
        </div>
      </div>

      {error && !snapshot && <p className="hint">Dashboard metrics unavailable.</p>}

      {/* Account health tiles */}
      <div className="metric-row">
        <div className="metric-card metric-card--accent">
          <span className="metric-label">Total accounts</span>
          <span className="metric-value">{acc.total ?? 0}</span>
        </div>
        {ACCOUNT_TILES.map((t) => (
          <div className="metric-card" key={t.key}>
            <span className="metric-label">{t.label}</span>
            <span className="metric-value">
              {acc[t.key] ?? 0} <span className={`dot dot--${t.tone}`} />
            </span>
          </div>
        ))}
      </div>

      <div className="card-grid">
        <section className="card">
          <div className="card-head">Sending throughput</div>
          <div className="stat">
            <span className="stat-value">{snapshot?.throughput.sends_last_hour ?? 0}</span>
            <span className="badge badge--muted">last hour</span>
          </div>
          <dl className="meta">
            <div>
              <dt>Sends (24h)</dt>
              <dd>{snapshot?.throughput.sends_today ?? 0}</dd>
            </div>
          </dl>
        </section>

        <section className="card">
          <div className="card-head">Today's sends vs caps</div>
          <div className="stat">
            <span className="stat-value">
              {caps?.actions_today ?? 0}
              <span className="hint-inline"> / {caps?.daily_cap ?? 0}</span>
            </span>
            <span className="badge badge--wait">{caps?.pct ?? 0}%</span>
          </div>
          <div className="progress">
            <div
              className="progress-fill"
              style={{ width: `${Math.min(100, caps?.pct ?? 0)}%` }}
            />
          </div>
        </section>

        <section className="card">
          <div className="card-head">Queue depth</div>
          <div className="stat">
            <span className="stat-value">{snapshot?.queue.total ?? 0}</span>
            <span className="badge badge--muted">waiting</span>
          </div>
          <dl className="meta">
            <div>
              <dt>Sender</dt>
              <dd>{snapshot?.queue.send_targets ?? 0}</dd>
            </div>
            <div>
              <dt>Campaigns</dt>
              <dd>{snapshot?.queue.campaign_targets ?? 0}</dd>
            </div>
          </dl>
        </section>

        <section className="card">
          <div className="card-head">Proxy-pool health</div>
          <div className="stat">
            <span className="stat-value">{proxies.total ?? 0}</span>
            <span className="badge badge--ok">{proxies.ok ?? 0} ok</span>
          </div>
          <dl className="meta">
            <div>
              <dt>Dead</dt>
              <dd>{proxies.dead ?? 0}</dd>
            </div>
            <div>
              <dt>Assigned</dt>
              <dd>{proxies.assigned ?? 0}</dd>
            </div>
            <div>
              <dt>Free</dt>
              <dd>{proxies.free ?? 0}</dd>
            </div>
          </dl>
        </section>

        <section className="card">
          <div className="card-head">Running campaigns</div>
          {snapshot && snapshot.running_campaigns.length === 0 && (
            <p className="hint">No campaigns running right now.</p>
          )}
          {snapshot?.running_campaigns.map((c) => (
            <div className="run-progress" key={c.id}>
              <div className="run-progress-top">
                <span className="run-progress-name">{c.name}</span>
                <span className="hint-inline">
                  {c.done}/{c.total}
                </span>
              </div>
              <div className="progress">
                <div
                  className="progress-fill"
                  style={{ width: `${c.total ? Math.round((100 * c.done) / c.total) : 0}%` }}
                />
              </div>
            </div>
          ))}
        </section>

        <section className="card">
          <div className="card-head">Recent quarantines & errors</div>
          {snapshot && snapshot.recent_events.length === 0 && (
            <p className="hint">No recent quarantines or flood events. All clear.</p>
          )}
          <ul className="event-feed">
            {snapshot?.recent_events.map((e) => (
              <li key={e.id}>
                <span className="badge badge--err">{e.type.replace('account.', '')}</span>
                <span className="event-ref">{e.entity_ref}</span>
                <span className="hint-inline">{timeAgo(e.created_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <p className="hint">
        See the <Link to="/analytics">Analytics</Link> page for funnel, per-source conversion,
        campaign A/B results, and the referral leaderboard.
      </p>
    </div>
  )
}
