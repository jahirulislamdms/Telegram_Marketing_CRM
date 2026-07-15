import { useEffect, useState, type FormEvent } from 'react'
import {
  ApiError,
  senderApi,
  type SendJob,
  type SendJobDetail,
} from '../api/client'

const JOB_BADGE: Record<string, string> = {
  draft: 'badge--muted',
  running: 'badge--ok',
  paused: 'badge--wait',
  done: 'badge--muted',
}

const TARGET_BADGE: Record<string, string> = {
  queued: 'badge--muted',
  sent: 'badge--ok',
  replied: 'badge--ok',
  failed: 'badge--err',
  skipped: 'badge--wait',
}

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

export default function Sender() {
  const [jobs, setJobs] = useState<SendJob[]>([])
  const [selected, setSelected] = useState<SendJobDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const loadJobs = async () => {
    try {
      setJobs(await senderApi.listJobs())
    } catch (e) {
      setError(errMsg(e))
    }
  }

  useEffect(() => {
    void loadJobs()
  }, [])

  const openJob = async (id: number) => {
    setNote(null)
    try {
      setSelected(await senderApi.getJob(id))
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const refresh = async () => {
    if (selected) setSelected(await senderApi.getJob(selected.id))
  }

  const control = async (fn: () => Promise<SendJobDetail>) => {
    setError(null)
    try {
      setSelected(await fn())
      await loadJobs()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const runTick = async () => {
    if (!selected) return
    setError(null)
    setNote(null)
    try {
      const r = await senderApi.tick(selected.id)
      setNote(
        `Tick: ${r.sent} sent, ${r.skipped} skipped, ${r.failed} failed` +
          (r.paused ? ` — auto-paused (${r.warning})` : ''),
      )
      await refresh()
      await loadJobs()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Sender</h1>
      <p className="page-subtitle">
        Paced outreach to consented contacts: account rotation, per-account caps, randomized
        delays, spintax, and auto-pause on flood warnings.
      </p>

      {error && <p className="form-error">{error}</p>}

      <div className="warmup-grid">
        <div>
          <CreateJobCard onCreated={loadJobs} onError={setError} />
          <section className="card">
            <div className="card-head">Jobs</div>
            {jobs.length === 0 ? (
              <p className="hint">No jobs yet.</p>
            ) : (
              <ul className="run-list">
                {jobs.map((j) => (
                  <li
                    key={j.id}
                    className={`run-item${selected?.id === j.id ? ' run-item--active' : ''}`}
                    onClick={() => openJob(j.id)}
                  >
                    <span>{j.name}</span>
                    <span className={`badge ${JOB_BADGE[j.status] ?? 'badge--muted'}`}>
                      {j.status}
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
              <p className="hint">Select a job to add targets and launch it.</p>
            </section>
          ) : (
            <JobDetail
              job={selected}
              note={note}
              onControl={control}
              onTick={runTick}
              onError={setError}
              onRefresh={refresh}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function CreateJobCard({
  onCreated,
  onError,
}: {
  onCreated: () => void
  onError: (m: string) => void
}) {
  const [name, setName] = useState('')
  const [template, setTemplate] = useState('')
  const [includeLink, setIncludeLink] = useState(false)
  const [linkUrl, setLinkUrl] = useState('')
  const [suppressFirst, setSuppressFirst] = useState(true)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await senderApi.createJob({
        name,
        template,
        include_link: includeLink,
        link_url: linkUrl || null,
        suppress_link_first: suppressFirst,
      })
      setName('')
      setTemplate('')
      setLinkUrl('')
      onCreated()
    } catch (err) {
      onError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <div className="card-head">New send job</div>
      <form className="field-block" onSubmit={submit}>
        <input placeholder="Job name" required value={name} onChange={(e) => setName(e.target.value)} />
        <textarea
          className="textarea"
          rows={3}
          placeholder={'Message with spintax, e.g. {Hi|Hello} there!'}
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
        />
        <label className="checkbox">
          <input type="checkbox" checked={includeLink} onChange={(e) => setIncludeLink(e.target.checked)} />
          <span>Include link</span>
        </label>
        {includeLink && (
          <>
            <input placeholder="https://link.url" value={linkUrl} onChange={(e) => setLinkUrl(e.target.value)} />
            <label className="checkbox">
              <input
                type="checkbox"
                checked={suppressFirst}
                onChange={(e) => setSuppressFirst(e.target.checked)}
              />
              <span>Suppress link in first-contact message</span>
            </label>
          </>
        )}
        <button className="btn btn-primary" type="submit" disabled={busy || !name || !template}>
          {busy ? 'Creating…' : 'Create job'}
        </button>
      </form>
    </section>
  )
}

function JobDetail({
  job,
  note,
  onControl,
  onTick,
  onError,
  onRefresh,
}: {
  job: SendJobDetail
  note: string | null
  onControl: (fn: () => Promise<SendJobDetail>) => void
  onTick: () => void
  onError: (m: string) => void
  onRefresh: () => Promise<void>
}) {
  const [source, setSource] = useState('')

  const addTargets = async (body: { contact_ids?: number[]; source?: string }) => {
    onError('')
    try {
      await senderApi.addTargets(job.id, body)
      await onRefresh()
    } catch (e) {
      onError(errMsg(e))
    }
  }

  const s = job.stats
  return (
    <>
      <section className="card">
        <div className="run-detail-head">
          <div>
            <h2 className="run-title">{job.name}</h2>
            <span className={`badge ${JOB_BADGE[job.status] ?? 'badge--muted'}`}>{job.status}</span>
          </div>
          <div className="run-controls">
            {job.status === 'draft' && (
              <button className="btn btn-primary btn-sm" onClick={() => onControl(() => senderApi.start(job.id))}>
                Start
              </button>
            )}
            {job.status === 'running' && (
              <>
                <button className="btn btn-ghost btn-sm" onClick={onTick}>
                  Run tick
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => onControl(() => senderApi.pause(job.id))}>
                  Pause
                </button>
              </>
            )}
            {job.status === 'paused' && (
              <button className="btn btn-primary btn-sm" onClick={() => onControl(() => senderApi.start(job.id))}>
                Resume
              </button>
            )}
            {job.status !== 'done' && (
              <button className="btn btn-ghost btn-sm" onClick={() => onControl(() => senderApi.stop(job.id))}>
                Stop
              </button>
            )}
          </div>
        </div>
        {note && <p className="hint">{note}</p>}
        <p className="hint">
          queued {s.queued ?? 0} · sent {s.sent ?? 0} · failed {s.failed ?? 0} · skipped{' '}
          {s.skipped ?? 0}
        </p>
      </section>

      <section className="card">
        <div className="card-head">Add targets (consented contacts only)</div>
        <div className="form-row">
          <input placeholder="Filter by source (optional)" value={source} onChange={(e) => setSource(e.target.value)} />
          <button className="btn btn-primary" onClick={() => addTargets(source ? { source } : {})}>
            Add contacts
          </button>
        </div>
      </section>

      <section className="card">
        <div className="card-head">Targets</div>
        {job.targets.length === 0 ? (
          <p className="hint">No targets yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Contact</th>
                  <th>Status</th>
                  <th>Sent by</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {job.targets.map((t) => (
                  <tr key={t.id}>
                    <td>{t.contact_label}</td>
                    <td>
                      <span className={`badge ${TARGET_BADGE[t.status] ?? 'badge--muted'}`}>
                        {t.status}
                      </span>
                    </td>
                    <td>{t.account_id ? `#${t.account_id}` : '—'}</td>
                    <td className="target-msg">{t.rendered_body || t.error || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
