import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  ApiError,
  CONTACT_STAGES,
  contactsApi,
  type Contact,
  type ContactImportResult,
  type ContactStage,
} from '../api/client'
import ContactMessageModal from '../components/ContactMessageModal'

const STAGE_BADGE: Record<string, string> = {
  new: 'badge--muted',
  contacted: 'badge--wait',
  replied: 'badge--ok',
  joined: 'badge--ok',
  customer: 'badge--ok',
  opted_out: 'badge--err',
}

const RES_BADGE: Record<string, string> = {
  resolved: 'badge--ok',
  pending: 'badge--muted',
  no_telegram: 'badge--wait',
  failed: 'badge--err',
}

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

export default function Contacts() {
  const [contacts, setContacts] = useState<Contact[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [stageFilter, setStageFilter] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [messageFor, setMessageFor] = useState<Contact | null>(null)
  const [importResult, setImportResult] = useState<ContactImportResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = {}
      if (q) params.q = q
      if (stageFilter) params.stage = stageFilter
      setContacts(await contactsApi.list(params))
      setSelected(new Set())
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stageFilter])

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const onImport = async (e: FormEvent) => {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    if (!file) return
    setError(null)
    try {
      const result = await contactsApi.importFile(file)
      setImportResult(result)
      if (fileRef.current) fileRef.current.value = ''
      await load()
    } catch (err) {
      setError(errMsg(err))
    }
  }

  const resolveOne = async (c: Contact) => {
    setError(null)
    try {
      await contactsApi.resolveOne(c.id)
      await load()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const bulkStage = async (stage: ContactStage) => {
    if (selected.size === 0) return
    try {
      await contactsApi.bulkStage([...selected], stage)
      await load()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const bulkDelete = async () => {
    if (selected.size === 0) return
    try {
      await contactsApi.bulkDelete([...selected])
      await load()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Contacts</h1>
      <p className="page-subtitle">
        Phone and username leads, CSV/Excel import with dedupe, consent tracking, and Telegram resolution.
      </p>

      {error && <p className="form-error">{error}</p>}

      <ImportCard fileRef={fileRef} onImport={onImport} result={importResult} onError={setError} />
      <AddContactCard onCreated={load} onError={setError} />

      <section className="card">
        <div className="contacts-toolbar">
          <input
            placeholder="Search name / @username / phone"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load()}
          />
          <select value={stageFilter} onChange={(e) => setStageFilter(e.target.value)}>
            <option value="">All stages</option>
            {CONTACT_STAGES.map((s) => (
              <option key={s} value={s}>
                {s.replace('_', ' ')}
              </option>
            ))}
          </select>
          <button className="btn btn-ghost btn-sm" onClick={load}>
            Search
          </button>
        </div>

        {selected.size > 0 && (
          <div className="bulk-bar">
            <span>{selected.size} selected</span>
            <select
              defaultValue=""
              onChange={(e) => e.target.value && bulkStage(e.target.value as ContactStage)}
            >
              <option value="">Set stage…</option>
              {CONTACT_STAGES.map((s) => (
                <option key={s} value={s}>
                  {s.replace('_', ' ')}
                </option>
              ))}
            </select>
            <button className="btn btn-ghost btn-sm" onClick={bulkDelete}>
              Delete
            </button>
          </div>
        )}

        {loading ? (
          <p className="hint">Loading…</p>
        ) : contacts.length === 0 ? (
          <p className="hint">No contacts. Import a CSV/Excel file or add one above.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th></th>
                  <th>Contact</th>
                  <th>Type</th>
                  <th>Stage</th>
                  <th>Resolution</th>
                  <th>Consent</th>
                  <th>Source</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {contacts.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.has(c.id)}
                        onChange={() => toggle(c.id)}
                      />
                    </td>
                    <td>{c.display_label}</td>
                    <td>{c.lead_type}</td>
                    <td>
                      <span className={`badge ${STAGE_BADGE[c.stage] ?? 'badge--muted'}`}>
                        {c.stage.replace('_', ' ')}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${RES_BADGE[c.resolution_status] ?? 'badge--muted'}`}>
                        {c.resolution_status.replace('_', ' ')}
                      </span>
                    </td>
                    <td>{c.consent ? '✓' : '—'}</td>
                    <td>{c.source || '—'}</td>
                    <td className="row-actions">
                      <button className="btn btn-ghost btn-sm" onClick={() => resolveOne(c)}>
                        Resolve
                      </button>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => setMessageFor(c)}
                        disabled={!c.consent || c.opted_out}
                      >
                        Message
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {messageFor && (
        <ContactMessageModal
          contact={messageFor}
          onClose={() => setMessageFor(null)}
          onSent={() => {
            setMessageFor(null)
            void load()
          }}
        />
      )}
    </div>
  )
}

function ImportCard({
  fileRef,
  onImport,
  result,
  onError,
}: {
  fileRef: React.RefObject<HTMLInputElement>
  onImport: (e: FormEvent) => void
  result: ContactImportResult | null
  onError: (m: string) => void
}) {
  const downloadTemplate = async () => {
    try {
      await contactsApi.downloadTemplate()
    } catch (e) {
      onError(errMsg(e))
    }
  }

  return (
    <section className="card">
      <div className="card-head">Import contacts</div>
      <form className="form-row" onSubmit={onImport}>
        <input ref={fileRef} type="file" accept=".csv,.xlsx,.xlsm" />
        <button className="btn btn-primary" type="submit">
          Import
        </button>
        <button type="button" className="btn btn-ghost" onClick={downloadTemplate}>
          Download template
        </button>
      </form>
      {result && (
        <p className="hint">
          Imported {result.imported}, skipped {result.skipped_duplicates} duplicate(s),{' '}
          {result.rejected_no_consent} without consent, {result.invalid} invalid.
        </p>
      )}
    </section>
  )
}

function AddContactCard({
  onCreated,
  onError,
}: {
  onCreated: () => void
  onError: (m: string) => void
}) {
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [username, setUsername] = useState('')
  const [source, setSource] = useState('')
  const [consent, setConsent] = useState(true)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await contactsApi.create({
        name: name || null,
        phone: phone || null,
        username: username || null,
        source: source || null,
        consent,
      })
      setName('')
      setPhone('')
      setUsername('')
      setSource('')
      onCreated()
    } catch (err) {
      onError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <div className="card-head">Add contact</div>
      <form className="form-row" onSubmit={submit}>
        <input placeholder="Name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="+phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <input placeholder="@username" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input placeholder="source" value={source} onChange={(e) => setSource(e.target.value)} />
        <label className="checkbox">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          <span>consent</span>
        </label>
        <button className="btn btn-primary" type="submit" disabled={busy}>
          Add
        </button>
      </form>
    </section>
  )
}
