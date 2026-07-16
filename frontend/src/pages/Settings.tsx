import { useCallback, useEffect, useState } from 'react'
import {
  ApiError,
  BACKUP_SCOPES,
  backupsApi,
  type BackupItem,
  type BackupSettings,
} from '../api/client'

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

const SCOPE_LABEL: Record<string, string> = {
  database: 'Database (all CRM data)',
  sessions: 'Accounts (Telegram sessions)',
  settings: 'Settings',
}

function humanSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export default function Settings() {
  const [items, setItems] = useState<BackupItem[]>([])
  const [scope, setScope] = useState<Set<string>>(new Set(BACKUP_SCOPES))
  const [cfg, setCfg] = useState<BackupSettings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const [list, settings] = await Promise.all([backupsApi.list(), backupsApi.getSettings()])
      setItems(list)
      setCfg(settings)
      setError(null)
    } catch (e) {
      setError(errMsg(e))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const toggleScope = (s: string) => {
    setScope((prev) => {
      const next = new Set(prev)
      if (next.has(s)) next.delete(s)
      else next.add(s)
      return next
    })
  }

  const create = async () => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const meta = await backupsApi.create([...scope])
      setNotice(`Backup created: ${meta.name} (${meta.scope.join(', ')})`)
      await load()
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const download = async (name: string) => {
    setError(null)
    try {
      await backupsApi.download(name)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const remove = async (name: string) => {
    if (!window.confirm(`Delete backup ${name} from the server?\n\nThis cannot be undone.`)) return
    setError(null)
    try {
      await backupsApi.remove(name)
      await load()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const restore = async (item: BackupItem) => {
    if (
      !window.confirm(
        `RESTORE ${item.name}?\n\n` +
          `This overwrites the current system with this backup (${item.scope.join(', ')}).\n` +
          'It is disruptive: data created since this backup will be lost, and you should ' +
          'restart the stack afterwards.\n\nContinue?',
      )
    )
      return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const res = await backupsApi.restore(item.name)
      setNotice(
        `Restored ${res.restored.join(', ')} from ${res.name}. Restart the stack to be safe.`,
      )
      await load()
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const saveSettings = async (patch: Partial<BackupSettings>) => {
    setError(null)
    try {
      setCfg(await backupsApi.saveSettings(patch))
      setNotice('Auto-backup settings saved.')
    } catch (e) {
      setError(errMsg(e))
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Settings</h1>
      <p className="page-subtitle">System settings. (Admin only.)</p>

      <h2 className="section-title">Backup &amp; Restore</h2>
      <p className="hint">
        Back up and restore everything in the system. Archives include your Telegram sessions
        and full database — keep them secret.
      </p>

      {error && <p className="form-error">{error}</p>}
      {notice && <p className="hint">{notice}</p>}

      <div className="card-grid">
        {/* Create */}
        <section className="card">
          <div className="card-head">Create a backup</div>
          <p className="hint">Choose what to include (everything by default).</p>
          {BACKUP_SCOPES.map((s) => (
            <label className="checkbox" key={s}>
              <input type="checkbox" checked={scope.has(s)} onChange={() => toggleScope(s)} />
              <span>{SCOPE_LABEL[s]}</span>
            </label>
          ))}
          <button
            className="btn btn-primary btn-block"
            onClick={create}
            disabled={busy || scope.size === 0}
          >
            {busy ? 'Working…' : 'Create backup'}
          </button>
        </section>

        {/* Auto-backup */}
        <section className="card">
          <div className="card-head">Automatic backups</div>
          {!cfg ? (
            <p className="hint">Loading…</p>
          ) : (
            <>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={cfg.enabled}
                  onChange={(e) => saveSettings({ enabled: e.target.checked })}
                />
                <span>Enable automatic backups</span>
              </label>
              <div className="form-row">
                <label className="hint-inline">Every</label>
                <input
                  type="number"
                  min={1}
                  max={365}
                  value={cfg.interval_days}
                  onChange={(e) => setCfg({ ...cfg, interval_days: Number(e.target.value) })}
                  style={{ maxWidth: 90 }}
                />
                <label className="hint-inline">day(s)</label>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => saveSettings({ interval_days: cfg.interval_days })}
                >
                  Save
                </button>
              </div>
              <p className="hint">
                {cfg.enabled
                  ? `Running every ${cfg.interval_days} day(s) — keeping the last 5.`
                  : 'Off — backups only run when you click Create.'}
              </p>
            </>
          )}
        </section>
      </div>

      {/* List */}
      <section className="card">
        <div className="card-head">Saved backups (last 5 kept)</div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Backup</th>
                <th>Created</th>
                <th>Size</th>
                <th>Includes</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((b) => (
                <tr key={b.name}>
                  <td>
                    <code>{b.name}</code>
                  </td>
                  <td>{new Date(b.created_at).toLocaleString()}</td>
                  <td>{humanSize(b.size)}</td>
                  <td>
                    {b.scope.map((s) => (
                      <span className="badge badge--muted" key={s}>
                        {s}
                      </span>
                    ))}
                  </td>
                  <td className="row-actions">
                    <button className="btn btn-ghost btn-sm" onClick={() => download(b.name)}>
                      Download
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => restore(b)}
                      disabled={busy}
                    >
                      Restore
                    </button>
                    <button
                      className="btn btn-ghost btn-sm btn-danger"
                      onClick={() => remove(b.name)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr>
                  <td colSpan={5} className="hint">
                    No backups yet. Create one above.
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
