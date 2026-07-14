import { useState } from 'react'
import {
  ApiError,
  accountsApi,
  type Account,
  type AccountStatusValue,
} from '../api/client'

interface Props {
  account: Account
  onClose: () => void
  onChanged: () => void
}

const STATUSES: AccountStatusValue[] = [
  'active',
  'warming',
  'quarantined',
  'banned',
  'logged_out',
]

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

export default function AccountHealthModal({ account, onClose, onChanged }: Props) {
  const [status, setStatus] = useState<AccountStatusValue>(
    account.status as AccountStatusValue,
  )
  const [spamState, setSpamState] = useState(account.spam_state)
  const [busy, setBusy] = useState<string | null>(null)
  const [log, setLog] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const loggedIn = Boolean(account.session_ref)

  const addLog = (line: string) => setLog((l) => [line, ...l].slice(0, 8))

  const applyStatus = async (next: AccountStatusValue) => {
    setError(null)
    setStatus(next)
    try {
      await accountsApi.setStatus(account.id, next)
      addLog(`Status set to "${next}".`)
      onChanged()
    } catch (e) {
      setError(errMsg(e))
      setStatus(account.status as AccountStatusValue)
    }
  }

  const run = async (name: string, fn: () => Promise<string>) => {
    setBusy(name)
    setError(null)
    try {
      addLog(await fn())
      onChanged()
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(null)
    }
  }

  const spamCheck = () =>
    run('spam', async () => {
      const r = await accountsApi.spamCheck(account.id)
      setSpamState(r.spam_state)
      return `Spam check: ${r.spam_state}${r.quarantined ? ' — auto-quarantined' : ''}.`
    })

  const banCheck = () =>
    run('ban', async () => {
      const r = await accountsApi.banCheck(account.id)
      return `Ban check: ${r.state} (status now "${r.status}").`
    })

  const unspam = () =>
    run('unspam', async () => {
      const r = await accountsApi.unspam(account.id)
      return `Unspam request ${r.submitted ? 'submitted' : 'sent (manual follow-up may be needed)'}.`
    })

  const unfreeze = () =>
    run('unfreeze', async () => {
      const r = await accountsApi.unfreeze(account.id)
      return `Unfreeze request ${r.submitted ? 'submitted' : 'sent'}.`
    })

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Health — {account.label}</h2>
          <button className="icon-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {error && <p className="form-error">{error}</p>}

        <div className="health-row">
          <span className="label">Spam state</span>
          <span className={`badge ${SPAM_BADGE[spamState] ?? 'badge--muted'}`}>{spamState}</span>
        </div>

        <div className="field-block">
          <span className="label">Manual status override</span>
          <select
            value={status}
            onChange={(e) => applyStatus(e.target.value as AccountStatusValue)}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace('_', ' ')}
              </option>
            ))}
          </select>
        </div>

        <div className="card-head" style={{ marginTop: 8 }}>
          Health checks
        </div>
        {!loggedIn && (
          <p className="hint">Account is not logged in — health checks are unavailable.</p>
        )}
        <div className="health-actions">
          <button className="btn btn-ghost" onClick={spamCheck} disabled={!loggedIn || busy !== null}>
            {busy === 'spam' ? 'Checking…' : 'Spam check'}
          </button>
          <button className="btn btn-ghost" onClick={banCheck} disabled={!loggedIn || busy !== null}>
            {busy === 'ban' ? 'Checking…' : 'Ban check'}
          </button>
          <button className="btn btn-ghost" onClick={unspam} disabled={!loggedIn || busy !== null}>
            {busy === 'unspam' ? 'Sending…' : 'Request unspam'}
          </button>
          <button className="btn btn-ghost" onClick={unfreeze} disabled={!loggedIn || busy !== null}>
            {busy === 'unfreeze' ? 'Sending…' : 'Request unfreeze'}
          </button>
        </div>

        {log.length > 0 && (
          <ul className="health-log">
            {log.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
