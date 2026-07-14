import { useEffect, useState, type FormEvent } from 'react'
import {
  ApiError,
  accountsApi,
  warmupApi,
  type Account,
  type WarmupRun,
  type WarmupRunDetail,
} from '../api/client'

const RUN_BADGE: Record<string, string> = {
  draft: 'badge--muted',
  running: 'badge--ok',
  paused: 'badge--wait',
  done: 'badge--muted',
}

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

export default function Warmup() {
  const [runs, setRuns] = useState<WarmupRun[]>([])
  const [selected, setSelected] = useState<WarmupRunDetail | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const loadRuns = async () => {
    try {
      setRuns(await warmupApi.listRuns())
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const openRun = async (id: number) => {
    setError(null)
    try {
      setSelected(await warmupApi.getRun(id))
      setAccounts(await accountsApi.list())
    } catch (e) {
      setError(errMsg(e))
    }
  }

  useEffect(() => {
    void loadRuns()
  }, [])

  const refreshSelected = async () => {
    if (selected) setSelected(await warmupApi.getRun(selected.id))
  }

  const control = async (fn: () => Promise<WarmupRunDetail>) => {
    setError(null)
    try {
      setSelected(await fn())
      await loadRuns()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const runTick = async () => {
    if (!selected) return
    setError(null)
    setNote(null)
    try {
      const r = await warmupApi.tick(selected.id)
      setNote(
        `Tick: ${r.actions.length} action(s), ${r.advanced} advanced, ${r.completed} completed` +
          (r.errors.length ? `, ${r.errors.length} error(s)` : ''),
      )
      await refreshSelected()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Warmup</h1>
      <p className="page-subtitle">
        Ramp new accounts safely: join groups and exchange casual messages with fleet peers and
        external partners, advancing through stages on a schedule.
      </p>

      {error && <p className="form-error">{error}</p>}

      <div className="warmup-grid">
        <div>
          <CreateRunCard onCreated={loadRuns} onError={setError} />
          <section className="card">
            <div className="card-head">Runs</div>
            {runs.length === 0 ? (
              <p className="hint">No runs yet.</p>
            ) : (
              <ul className="run-list">
                {runs.map((r) => (
                  <li
                    key={r.id}
                    className={`run-item${selected?.id === r.id ? ' run-item--active' : ''}`}
                    onClick={() => openRun(r.id)}
                  >
                    <span>{r.name}</span>
                    <span className={`badge ${RUN_BADGE[r.status] ?? 'badge--muted'}`}>
                      {r.status}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <div>
          {!selected ? (
            <section className="card">
              <p className="hint">Select a run to configure and launch it.</p>
            </section>
          ) : (
            <RunDetail
              run={selected}
              accounts={accounts}
              note={note}
              onControl={control}
              onTick={runTick}
              onError={setError}
              onRefresh={refreshSelected}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function CreateRunCard({
  onCreated,
  onError,
}: {
  onCreated: () => void
  onError: (m: string) => void
}) {
  const [name, setName] = useState('')
  const [groups, setGroups] = useState('')
  const [messages, setMessages] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await warmupApi.createRun({
        name,
        groups: groups.split('\n').map((s) => s.trim()).filter(Boolean),
        messages: messages.split('\n').map((s) => s.trim()).filter(Boolean),
      })
      setName('')
      setGroups('')
      setMessages('')
      onCreated()
    } catch (err) {
      onError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <div className="card-head">New run</div>
      <form className="field-block" onSubmit={submit}>
        <input
          placeholder="Run name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <textarea
          className="textarea"
          rows={2}
          placeholder="Group/channel links to join (one per line)"
          value={groups}
          onChange={(e) => setGroups(e.target.value)}
        />
        <textarea
          className="textarea"
          rows={3}
          placeholder="Chit-chat messages (one per line)"
          value={messages}
          onChange={(e) => setMessages(e.target.value)}
        />
        <button className="btn btn-primary" type="submit" disabled={busy || !name}>
          {busy ? 'Creating…' : 'Create run'}
        </button>
      </form>
    </section>
  )
}

function RunDetail({
  run,
  accounts,
  note,
  onControl,
  onTick,
  onError,
  onRefresh,
}: {
  run: WarmupRunDetail
  accounts: Account[]
  note: string | null
  onControl: (fn: () => Promise<WarmupRunDetail>) => void
  onTick: () => void
  onError: (m: string) => void
  onRefresh: () => Promise<void>
}) {
  const [partnerId, setPartnerId] = useState('')
  const [partnerKind, setPartnerKind] = useState<'phone' | 'username'>('username')
  const [pickAccount, setPickAccount] = useState('')

  const participantAccountIds = new Set(run.participants.map((p) => p.account_id))
  const available = accounts.filter((a) => !participantAccountIds.has(a.id))

  const addPartner = async () => {
    onError('')
    try {
      await warmupApi.addPartner(run.id, partnerId.trim(), partnerKind)
      setPartnerId('')
      await onRefresh()
    } catch (e) {
      onError(errMsg(e))
    }
  }

  const addParticipant = async () => {
    if (!pickAccount) return
    try {
      await warmupApi.addParticipants(run.id, [Number(pickAccount)])
      setPickAccount('')
      await onRefresh()
    } catch (e) {
      onError(errMsg(e))
    }
  }

  const removeParticipant = async (pid: number) => {
    try {
      await warmupApi.removeParticipant(run.id, pid)
      await onRefresh()
    } catch (e) {
      onError(errMsg(e))
    }
  }

  return (
    <>
      <section className="card">
        <div className="run-detail-head">
          <div>
            <h2 className="run-title">{run.name}</h2>
            <span className={`badge ${RUN_BADGE[run.status] ?? 'badge--muted'}`}>
              {run.status}
            </span>
          </div>
          <div className="run-controls">
            {run.status === 'draft' && (
              <button className="btn btn-primary btn-sm" onClick={() => onControl(() => warmupApi.start(run.id))}>
                Start
              </button>
            )}
            {run.status === 'running' && (
              <>
                <button className="btn btn-ghost btn-sm" onClick={onTick}>
                  Run tick
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => onControl(() => warmupApi.pause(run.id))}>
                  Pause
                </button>
              </>
            )}
            {run.status === 'paused' && (
              <button className="btn btn-primary btn-sm" onClick={() => onControl(() => warmupApi.start(run.id))}>
                Resume
              </button>
            )}
            {run.status !== 'done' && (
              <button className="btn btn-ghost btn-sm" onClick={() => onControl(() => warmupApi.stop(run.id))}>
                Stop
              </button>
            )}
          </div>
        </div>
        {note && <p className="hint">{note}</p>}
        <p className="hint">
          Stages: {run.stages.map((s) => `${s.days}d×${s.max_actions}`).join(' → ')} · groups:{' '}
          {run.groups.length} · messages: {run.messages.length}
        </p>
      </section>

      <section className="card">
        <div className="card-head">Fleet accounts ({run.participants.length})</div>
        <div className="form-row">
          <select value={pickAccount} onChange={(e) => setPickAccount(e.target.value)}>
            <option value="">Select an account…</option>
            {available.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
          <button className="btn btn-primary" onClick={addParticipant} disabled={!pickAccount}>
            Add
          </button>
        </div>
        {run.participants.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Stage</th>
                  <th>Today</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {run.participants.map((p) => (
                  <tr key={p.id}>
                    <td>{p.account_label}</td>
                    <td>stage {p.stage_progress}</td>
                    <td>{p.actions_today}</td>
                    <td>
                      <span className="badge badge--muted">{p.status}</span>
                    </td>
                    <td className="row-actions">
                      <button className="btn btn-ghost btn-sm" onClick={() => removeParticipant(p.id)}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-head">External partners ({run.partners.length})</div>
        <p className="hint">
          Not logged in — the fleet messages them; you reply manually from that account.
        </p>
        <div className="form-row">
          <input
            placeholder="@username or +phone"
            value={partnerId}
            onChange={(e) => setPartnerId(e.target.value)}
          />
          <select value={partnerKind} onChange={(e) => setPartnerKind(e.target.value as 'phone' | 'username')}>
            <option value="username">username</option>
            <option value="phone">phone</option>
          </select>
          <button className="btn btn-primary" onClick={addPartner} disabled={partnerId.trim().length < 2}>
            Add partner
          </button>
        </div>
        {run.partners.length > 0 && (
          <ul className="chip-list">
            {run.partners.map((p) => (
              <li key={p.id} className="chip">
                {p.identifier} <small>({p.kind})</small>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
