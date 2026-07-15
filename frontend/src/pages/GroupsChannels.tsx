import { useEffect, useState, type FormEvent } from 'react'
import {
  ApiError,
  contactsApi,
  destinationsApi,
  type Contact,
  type Destination,
  type DestinationDetail,
} from '../api/client'

const STATE_BADGE: Record<string, string> = {
  pending: 'badge--muted',
  added: 'badge--ok',
  invited: 'badge--wait',
  joined: 'badge--ok',
  failed: 'badge--err',
}

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

export default function GroupsChannels() {
  const [destinations, setDestinations] = useState<Destination[]>([])
  const [selected, setSelected] = useState<DestinationDetail | null>(null)
  const [contacts, setContacts] = useState<Contact[]>([])
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const load = async () => {
    try {
      setDestinations(await destinationsApi.list())
    } catch (e) {
      setError(errMsg(e))
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const open = async (id: number) => {
    setNote(null)
    try {
      setSelected(await destinationsApi.get(id))
      setContacts((await contactsApi.list()).filter((c) => c.consent && !c.opted_out))
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const refresh = async () => {
    if (selected) setSelected(await destinationsApi.get(selected.id))
  }

  const runTick = async () => {
    if (!selected) return
    setError(null)
    setNote(null)
    try {
      const r = await destinationsApi.tick(selected.id)
      setNote(
        `Tick: ${r.added} added, ${r.invited} invited, ${r.failed} failed` +
          (r.paused ? ` — auto-paused (${r.warning})` : ''),
      )
      await refresh()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Groups &amp; Channels</h1>
      <p className="page-subtitle">
        Register destinations and add members — direct-add with automatic invite-link fallback,
        excluding contacts already in the group.
      </p>

      {error && <p className="form-error">{error}</p>}

      <div className="warmup-grid">
        <div>
          <RegisterCard onRegistered={load} onError={setError} />
          <section className="card">
            <div className="card-head">Destinations</div>
            {destinations.length === 0 ? (
              <p className="hint">No destinations yet.</p>
            ) : (
              <ul className="run-list">
                {destinations.map((d) => (
                  <li
                    key={d.id}
                    className={`run-item${selected?.id === d.id ? ' run-item--active' : ''}`}
                    onClick={() => open(d.id)}
                  >
                    <span>{d.title || d.link}</span>
                    <span className={`badge ${d.tg_entity_id ? 'badge--ok' : 'badge--wait'}`}>
                      {d.tg_entity_id ? d.type : 'unresolved'}
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
              <p className="hint">Select a destination to add members.</p>
            </section>
          ) : (
            <DestinationDetailView
              destination={selected}
              contacts={contacts}
              note={note}
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

function RegisterCard({
  onRegistered,
  onError,
}: {
  onRegistered: () => void
  onError: (m: string) => void
}) {
  const [link, setLink] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await destinationsApi.register(link)
      setLink('')
      onRegistered()
    } catch (err) {
      onError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <div className="card-head">Register destination</div>
      <form className="form-row" onSubmit={submit}>
        <input placeholder="https://t.me/group_or_channel" required value={link} onChange={(e) => setLink(e.target.value)} />
        <button className="btn btn-primary" type="submit" disabled={busy || !link}>
          {busy ? 'Adding…' : 'Register'}
        </button>
      </form>
    </section>
  )
}

function DestinationDetailView({
  destination,
  contacts,
  note,
  onTick,
  onError,
  onRefresh,
}: {
  destination: DestinationDetail
  contacts: Contact[]
  note: string | null
  onTick: () => void
  onError: (m: string) => void
  onRefresh: () => Promise<void>
}) {
  const [identifiers, setIdentifiers] = useState('')
  const [picked, setPicked] = useState<Set<number>>(new Set())

  const alreadyIn = new Set(
    destination.memberships
      .filter((m) => ['added', 'invited', 'joined'].includes(m.state))
      .map((m) => m.contact_id),
  )

  const toggle = (id: number) => {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const addMembers = async () => {
    onError('')
    const ids = [...picked]
    const typed = identifiers.split('\n').map((s) => s.trim()).filter(Boolean)
    if (ids.length === 0 && typed.length === 0) return
    try {
      await destinationsApi.addMembers(destination.id, {
        contact_ids: ids.length ? ids : undefined,
        identifiers: typed.length ? typed : undefined,
      })
      setIdentifiers('')
      setPicked(new Set())
      await onRefresh()
    } catch (e) {
      onError(errMsg(e))
    }
  }

  const s = destination.stats
  return (
    <>
      <section className="card">
        <div className="run-detail-head">
          <div>
            <h2 className="run-title">{destination.title || destination.link}</h2>
            <span className={`badge ${destination.tg_entity_id ? 'badge--ok' : 'badge--wait'}`}>
              {destination.tg_entity_id ? destination.type : 'unresolved'}
            </span>
          </div>
          <div className="run-controls">
            {destination.tg_entity_id && (
              <button className="btn btn-primary btn-sm" onClick={onTick}>
                Run add
              </button>
            )}
          </div>
        </div>
        {note && <p className="hint">{note}</p>}
        <p className="hint">
          pending {s.pending ?? 0} · added {s.added ?? 0} · invited {s.invited ?? 0} · failed{' '}
          {s.failed ?? 0}
        </p>
      </section>

      <section className="card">
        <div className="card-head">Build member list</div>
        <p className="hint">Pick consented contacts and/or type usernames/numbers (one per line).</p>
        <div className="member-picker">
          {contacts.map((c) => (
            <label key={c.id} className={`member-chip${alreadyIn.has(c.id) ? ' member-chip--in' : ''}`}>
              <input
                type="checkbox"
                checked={picked.has(c.id)}
                disabled={alreadyIn.has(c.id)}
                onChange={() => toggle(c.id)}
              />
              <span>{c.display_label}</span>
              {alreadyIn.has(c.id) && <small>in group</small>}
            </label>
          ))}
        </div>
        <textarea
          className="textarea"
          rows={2}
          placeholder={'@username\n+15551234567'}
          value={identifiers}
          onChange={(e) => setIdentifiers(e.target.value)}
        />
        <button className="btn btn-primary" onClick={addMembers}>
          Add to queue
        </button>
      </section>

      <section className="card">
        <div className="card-head">Members</div>
        {destination.memberships.length === 0 ? (
          <p className="hint">No members queued yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Contact</th>
                  <th>State</th>
                  <th>Method</th>
                  <th>By</th>
                </tr>
              </thead>
              <tbody>
                {destination.memberships.map((m) => (
                  <tr key={m.id}>
                    <td>{m.contact_label}</td>
                    <td>
                      <span className={`badge ${STATE_BADGE[m.state] ?? 'badge--muted'}`}>
                        {m.state}
                      </span>
                    </td>
                    <td>{m.method || '—'}</td>
                    <td>{m.account_id ? `#${m.account_id}` : '—'}</td>
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
