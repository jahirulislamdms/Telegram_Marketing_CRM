import { useEffect, useState, type FormEvent } from 'react'
import {
  ApiError,
  accountsApi,
  proxiesApi,
  type Account,
  type Proxy,
} from '../api/client'
import AccountHealthModal from '../components/AccountHealthModal'
import AccountLoginModal from '../components/AccountLoginModal'
import AccountEditModal from '../components/AccountEditModal'

const STATUS_BADGE: Record<string, string> = {
  active: 'badge--ok',
  warming: 'badge--wait',
  quarantined: 'badge--err',
  banned: 'badge--err',
  logged_out: 'badge--muted',
}

const SPAM_BADGE: Record<string, string> = {
  clean: 'badge--ok',
  limited: 'badge--wait',
  banned: 'badge--err',
  unknown: 'badge--muted',
}

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

export default function Accounts() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [proxies, setProxies] = useState<Proxy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loginFor, setLoginFor] = useState<Account | null>(null)
  const [healthFor, setHealthFor] = useState<Account | null>(null)
  const [editFor, setEditFor] = useState<Account | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const [a, p] = await Promise.all([accountsApi.list(), proxiesApi.list()])
      setAccounts(a)
      setProxies(p)
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const proxyLabel = (id: number | null): string => {
    if (id === null) return 'none'
    const p = proxies.find((x) => x.id === id)
    return p ? `${p.host}:${p.port}` : `#${id}`
  }

  const onLogout = async (a: Account) => {
    setError(null)
    try {
      await accountsApi.logout(a.id)
      await load()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const onRemove = async (a: Account) => {
    setError(null)
    try {
      await accountsApi.remove(a.id)
      await load()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Accounts</h1>
      <p className="page-subtitle">
        Register Telegram accounts, log them in (QR / phone / session), and bind a proxy from the pool.
      </p>

      {error && <p className="form-error">{error}</p>}

      <AddAccountCard
        hasProxies={proxies.length > 0}
        onCreated={load}
        onError={setError}
      />

      <section className="card">
        <div className="card-head">Accounts</div>
        {loading ? (
          <p className="hint">Loading…</p>
        ) : accounts.length === 0 ? (
          <p className="hint">No accounts yet. Add one above.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Telegram identity</th>
                  <th>Status</th>
                  <th>Spam</th>
                  <th>Proxy</th>
                  <th>Today</th>
                  <th className="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.id}>
                    <td>{a.label}</td>
                    <td>
                      {/* The account's real Telegram identity (§15.6). */}
                      <div className="tg-cell">
                        {a.tg_first_name && <span className="tg-cell-name">{a.tg_first_name}</span>}
                        {a.tg_username && <span className="tg-cell-user">@{a.tg_username}</span>}
                        {a.phone && <span className="tg-cell-phone">{a.phone}</span>}
                        {!a.tg_first_name && !a.tg_username && !a.phone && (
                          <span className="tg-cell-unknown">
                            {a.session_ref ? 'unknown — run Health' : 'not logged in'}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={`badge ${STATUS_BADGE[a.status] ?? 'badge--muted'}`}>
                        {a.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${SPAM_BADGE[a.spam_state] ?? 'badge--muted'}`}>
                        {a.spam_state}
                      </span>
                    </td>
                    <td>{proxyLabel(a.proxy_id)}</td>
                    <td>
                      {a.actions_today}/{a.daily_cap}
                    </td>
                    <td className="col-actions">
                      <div className="quick-actions">
                        {a.session_ref ? (
                          <button className="btn btn-ghost btn-sm" onClick={() => onLogout(a)}>
                            Log out
                          </button>
                        ) : (
                          <button className="btn btn-primary btn-sm" onClick={() => setLoginFor(a)}>
                            Log in
                          </button>
                        )}
                        {/* One unified Edit covers name + proxy (§15.6). */}
                        <button className="icon-btn" title="Edit account" onClick={() => setEditFor(a)}>
                          ✏️
                        </button>
                        <button className="btn btn-ghost btn-sm" onClick={() => setHealthFor(a)}>
                          Health
                        </button>
                        <button className="btn btn-ghost btn-sm" onClick={() => onRemove(a)}>
                          Remove
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <ProxyPoolCard proxies={proxies} onChange={load} onError={setError} />

      {loginFor && (
        <AccountLoginModal
          account={loginFor}
          onClose={() => setLoginFor(null)}
          onSuccess={() => {
            setLoginFor(null)
            void load()
          }}
        />
      )}

      {healthFor && (
        <AccountHealthModal
          account={healthFor}
          onClose={() => setHealthFor(null)}
          onChanged={load}
        />
      )}

      {editFor && (
        <AccountEditModal
          account={editFor}
          proxies={proxies}
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

function AddAccountCard({
  hasProxies,
  onCreated,
  onError,
}: {
  hasProxies: boolean
  onCreated: () => void
  onError: (m: string) => void
}) {
  const [label, setLabel] = useState('')
  const [phone, setPhone] = useState('')
  const [assignProxy, setAssignProxy] = useState(true)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await accountsApi.create({
        label,
        phone: phone || null,
        assign_proxy: assignProxy,
      })
      setLabel('')
      setPhone('')
      onCreated()
    } catch (err) {
      onError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <div className="card-head">Add account</div>
      <form className="form-row" onSubmit={submit}>
        <input
          placeholder="Label (e.g. Sales 1)"
          required
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <input
          type="tel"
          placeholder="Phone (optional)"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
        <label className="checkbox">
          <input
            type="checkbox"
            checked={assignProxy}
            onChange={(e) => setAssignProxy(e.target.checked)}
          />
          <span>Assign proxy{!hasProxies ? ' (pool empty)' : ''}</span>
        </label>
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? 'Adding…' : 'Add'}
        </button>
      </form>
    </section>
  )
}

function ProxyPoolCard({
  proxies,
  onChange,
  onError,
}: {
  proxies: Proxy[]
  onChange: () => void
  onError: (m: string) => void
}) {
  const [raw, setRaw] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setResult(null)
    try {
      const r = await proxiesApi.import(raw)
      setResult(
        `Imported ${r.imported}, skipped ${r.skipped_duplicates} duplicate(s), ${r.invalid.length} invalid.`,
      )
      setRaw('')
      onChange()
    } catch (e) {
      onError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const free = proxies.filter((p) => p.assigned_account_id === null).length

  return (
    <section className="card">
      <div className="card-head">
        Proxy pool <span className="hint-inline">({proxies.length} total · {free} free)</span>
      </div>
      <textarea
        className="textarea"
        rows={3}
        placeholder={'host:port\nhost:port:user:pass\nsocks5://user:pass@host:port'}
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
      />
      <div className="row-actions-left">
        <button className="btn btn-primary" onClick={submit} disabled={busy || !raw.trim()}>
          {busy ? 'Importing…' : 'Import proxies'}
        </button>
        {result && <span className="hint">{result}</span>}
      </div>

      {proxies.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Host</th>
                <th>Port</th>
                <th>Health</th>
                <th>Assigned</th>
              </tr>
            </thead>
            <tbody>
              {proxies.map((p) => (
                <tr key={p.id}>
                  <td>{p.type}</td>
                  <td>{p.host}</td>
                  <td>{p.port}</td>
                  <td>
                    <span
                      className={`badge ${
                        p.health === 'ok'
                          ? 'badge--ok'
                          : p.health === 'dead'
                            ? 'badge--err'
                            : 'badge--muted'
                      }`}
                    >
                      {p.health}
                    </span>
                  </td>
                  <td>{p.assigned_account_id ? `account #${p.assigned_account_id}` : 'free'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
