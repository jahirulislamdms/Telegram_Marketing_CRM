import { useCallback, useEffect, useState } from 'react'
import {
  analyticsApi,
  type AnalyticsOverview,
  type ReferralDetail,
} from '../api/client'

const FUNNEL_STEPS: Array<{ key: string; label: string }> = [
  { key: 'contacted', label: 'Contacted' },
  { key: 'replied', label: 'Replied' },
  { key: 'joined', label: 'Joined' },
  { key: 'customer', label: 'Customer' },
]

const SOURCE_STAGES = ['new', 'contacted', 'replied', 'joined', 'customer', 'opted_out']

export default function Analytics() {
  const [data, setData] = useState<AnalyticsOverview | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [subscriberId, setSubscriberId] = useState('')
  const [createdLink, setCreatedLink] = useState<ReferralDetail | null>(null)
  const [recordCode, setRecordCode] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await analyticsApi.overview())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load analytics')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const createReferral = async () => {
    const id = Number(subscriberId)
    if (!Number.isFinite(id) || id <= 0) return
    setNotice(null)
    try {
      const detail = await analyticsApi.createReferral(id)
      setCreatedLink(detail)
      await load()
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Could not create referral')
    }
  }

  const recordReferral = async () => {
    if (!recordCode.trim()) return
    setNotice(null)
    try {
      const r = await analyticsApi.recordReferral(recordCode.trim())
      setNotice(`Recorded — code ${r.invite_code} now has ${r.invited_count} invite(s).`)
      setRecordCode('')
      await load()
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Unknown invite code')
    }
  }

  const reward = async (id: number, rewarded: boolean) => {
    await analyticsApi.reward(id, rewarded)
    await load()
  }

  const funnel = data?.funnel
  const funnelBase = funnel?.reached.contacted || 0

  return (
    <div className="page">
      <h1 className="page-title">Analytics</h1>
      <p className="page-subtitle">
        Funnel, per-source conversion, campaign A/B results, UTM attribution, and referrals.
      </p>
      {error && <p className="hint">{error}</p>}

      {/* Funnel */}
      <section className="card">
        <div className="card-head">
          Conversion funnel
          {funnel && (
            <span className="hint-inline"> · {funnel.conversion_pct}% contacted → customer</span>
          )}
        </div>
        <div className="funnel">
          {FUNNEL_STEPS.map((step) => {
            const value = funnel?.reached[step.key] ?? 0
            const pct = funnelBase ? Math.round((100 * value) / funnelBase) : 0
            return (
              <div className="funnel-row" key={step.key}>
                <span className="funnel-label">{step.label}</span>
                <div className="funnel-bar">
                  <div className="funnel-fill" style={{ width: `${pct}%` }}>
                    <span className="funnel-count">{value}</span>
                  </div>
                </div>
                <span className="funnel-pct">{pct}%</span>
              </div>
            )
          })}
        </div>
      </section>

      {/* Per-source conversion */}
      <section className="card">
        <div className="card-head">Per-source conversion</div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Total</th>
                {SOURCE_STAGES.map((s) => (
                  <th key={s}>{s}</th>
                ))}
                <th>Conv.</th>
              </tr>
            </thead>
            <tbody>
              {data?.per_source.map((row) => (
                <tr key={row.source}>
                  <td>{row.source}</td>
                  <td>{row.total}</td>
                  {SOURCE_STAGES.map((s) => (
                    <td key={s}>{(row[s] as number) ?? 0}</td>
                  ))}
                  <td>
                    <span className="badge badge--ok">{row.conversion_pct}%</span>
                  </td>
                </tr>
              ))}
              {data && data.per_source.length === 0 && (
                <tr>
                  <td colSpan={SOURCE_STAGES.length + 3} className="hint">
                    No contacts yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Campaign & A/B performance */}
      <section className="card">
        <div className="card-head">Campaign & A/B performance</div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Campaign</th>
                <th>Action</th>
                <th>Status</th>
                <th>A/B</th>
                <th>Targets</th>
                <th>Sent</th>
                <th>Joined</th>
                <th>Replied</th>
                <th>Failed</th>
              </tr>
            </thead>
            <tbody>
              {data?.campaigns.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{c.action}</td>
                  <td>
                    <span className="badge badge--muted">{c.status}</span>
                  </td>
                  <td>{c.ab_test ? 'yes' : '—'}</td>
                  <td>{c.targets}</td>
                  <td>{c.sent}</td>
                  <td>{c.joined}</td>
                  <td>{c.replied}</td>
                  <td>{c.failed}</td>
                </tr>
              ))}
              {data && data.campaigns.length === 0 && (
                <tr>
                  <td colSpan={9} className="hint">
                    No campaigns yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* UTM attribution */}
      <section className="card">
        <div className="card-head">UTM attribution (bot deep-links)</div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>UTM source</th>
                <th>Subscribers</th>
                <th>Subscribed</th>
                <th>Converted</th>
              </tr>
            </thead>
            <tbody>
              {data?.utm.map((u) => (
                <tr key={u.utm_source}>
                  <td>{u.utm_source}</td>
                  <td>{u.subscribers}</td>
                  <td>{u.subscribed}</td>
                  <td>{u.converted}</td>
                </tr>
              ))}
              {data && data.utm.length === 0 && (
                <tr>
                  <td colSpan={4} className="hint">
                    No bot subscribers yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Referral program */}
      <section className="card">
        <div className="card-head">Referral leaderboard</div>
        <div className="referral-tools">
          <div className="form-row">
            <input
              placeholder="Subscriber ID"
              value={subscriberId}
              onChange={(e) => setSubscriberId(e.target.value)}
            />
            <button className="btn btn-primary btn-sm" onClick={createReferral}>
              Create referral link
            </button>
          </div>
          <div className="form-row">
            <input
              placeholder="Invite code (record a referral)"
              value={recordCode}
              onChange={(e) => setRecordCode(e.target.value)}
            />
            <button className="btn btn-ghost btn-sm" onClick={recordReferral}>
              Record referral
            </button>
          </div>
        </div>
        {createdLink && (
          <p className="hint">
            Referral link for subscriber {createdLink.referrer_subscriber_id}:{' '}
            <code>{createdLink.deep_link}</code>
          </p>
        )}
        {notice && <p className="hint">{notice}</p>}
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Referrer</th>
                <th>Bot</th>
                <th>Invite code</th>
                <th>Invited</th>
                <th>Rewarded</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data?.referrals.map((r) => (
                <tr key={r.referral_id}>
                  <td>{r.label}</td>
                  <td>{r.bot_name || '—'}</td>
                  <td>
                    <code>{r.invite_code}</code>
                  </td>
                  <td>{r.invited_count}</td>
                  <td>{r.rewarded ? '✓' : '—'}</td>
                  <td className="row-actions">
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => reward(r.referral_id, !r.rewarded)}
                    >
                      {r.rewarded ? 'Unreward' : 'Reward'}
                    </button>
                  </td>
                </tr>
              ))}
              {data && data.referrals.length === 0 && (
                <tr>
                  <td colSpan={6} className="hint">
                    No referrals yet. Create a referral link for a bot subscriber to start.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
