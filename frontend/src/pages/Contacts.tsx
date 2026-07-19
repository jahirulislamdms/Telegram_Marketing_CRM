import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
  ApiError,
  CONTACT_STAGES,
  contactsApi,
  type Contact,
  type ContactImportResult,
  type ContactStage,
} from '../api/client'
import ContactMessageModal from '../components/ContactMessageModal'
import ContactEditModal from '../components/ContactEditModal'

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

const PAGE_SIZES = [10, 25, 50, 100]

const AVATAR_HUES = [210, 160, 280, 20, 340, 130, 45, 190]

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

function initials(c: Contact): string {
  const base = c.name || c.username || c.phone || '?'
  const parts = base.replace(/^[@+]/, '').trim().split(/\s+/)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return base.replace(/^[@+]/, '').slice(0, 2).toUpperCase()
}

function Avatar({ c }: { c: Contact }) {
  const hue = AVATAR_HUES[c.id % AVATAR_HUES.length]
  return (
    <span
      className="c-avatar"
      style={{ background: `hsl(${hue} 60% 45%)` }}
      aria-hidden
    >
      {initials(c)}
    </span>
  )
}

export default function Contacts() {
  const [contacts, setContacts] = useState<Contact[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // filters
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [stageFilter, setStageFilter] = useState('')
  const [leadTypeFilter, setLeadTypeFilter] = useState('')
  const [resolutionFilter, setResolutionFilter] = useState('')
  const [consentFilter, setConsentFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [sourceOptions, setSourceOptions] = useState<string[]>([])

  // pagination
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)

  // selection / modals
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [messageFor, setMessageFor] = useState<Contact | null>(null)
  const [editFor, setEditFor] = useState<Contact | null>(null)
  const [importResult, setImportResult] = useState<ContactImportResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const filterParams = useMemo(() => {
    const p: Record<string, string> = {}
    if (debouncedQ) p.q = debouncedQ
    if (stageFilter) p.stage = stageFilter
    if (leadTypeFilter) p.lead_type = leadTypeFilter
    if (resolutionFilter) p.resolution = resolutionFilter
    if (consentFilter) p.consent = consentFilter
    if (sourceFilter) p.source = sourceFilter
    return p
  }, [debouncedQ, stageFilter, leadTypeFilter, resolutionFilter, consentFilter, sourceFilter])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, string> = {
        ...filterParams,
        limit: String(pageSize),
        offset: String((page - 1) * pageSize),
      }
      const { items, total: t } = await contactsApi.listPage(params)
      setContacts(items)
      setTotal(t)
      // accumulate distinct sources for the source filter datalist
      setSourceOptions((prev) => {
        const set = new Set(prev)
        items.forEach((c) => c.source && set.add(c.source))
        return [...set].sort()
      })
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setLoading(false)
    }
  }, [filterParams, page, pageSize])

  useEffect(() => {
    void load()
  }, [load])

  // debounce the search box → instant-feeling but not a request per keystroke
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 300)
    return () => clearTimeout(t)
  }, [q])

  // any filter change resets to page 1
  useEffect(() => {
    setPage(1)
  }, [debouncedQ, stageFilter, leadTypeFilter, resolutionFilter, consentFilter, sourceFilter, pageSize])

  const pageIds = contacts.map((c) => c.id)
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id))

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const togglePage = () => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (allPageSelected) pageIds.forEach((id) => next.delete(id))
      else pageIds.forEach((id) => next.add(id))
      return next
    })
  }

  const clearSelection = () => setSelected(new Set())

  const selectAllMatching = async () => {
    try {
      const all = await contactsApi.list(filterParams)
      setSelected(new Set(all.map((c) => c.id)))
    } catch (e) {
      setError(errMsg(e))
    }
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

  const deleteOne = async (c: Contact) => {
    if (!window.confirm(`Delete ${c.display_label}?`)) return
    try {
      await contactsApi.remove(c.id)
      setSelected((prev) => {
        const n = new Set(prev)
        n.delete(c.id)
        return n
      })
      await load()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const runExport = async (format: 'csv' | 'xlsx', scope: 'all' | 'filtered' | 'selected') => {
    try {
      if (scope === 'selected') await contactsApi.exportFile(format, { ids: [...selected].join(',') })
      else if (scope === 'filtered') await contactsApi.exportFile(format, filterParams)
      else await contactsApi.exportFile(format, {})
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const runBulk = async (action: string) => {
    const ids = [...selected]
    if (ids.length === 0) return
    try {
      if (action.startsWith('stage:')) {
        await contactsApi.bulkStage(ids, action.slice(6) as ContactStage)
      } else if (action === 'consent:on') {
        await contactsApi.bulkConsent(ids, true)
      } else if (action === 'consent:off') {
        await contactsApi.bulkConsent(ids, false)
      } else if (action === 'resolve') {
        await contactsApi.bulkResolve(ids)
      } else if (action === 'unresolve') {
        await contactsApi.bulkUnresolve(ids)
      } else if (action === 'export:csv') {
        await runExport('csv', 'selected')
        return
      } else if (action === 'export:xlsx') {
        await runExport('xlsx', 'selected')
        return
      } else if (action === 'delete') {
        if (!window.confirm(`Delete ${ids.length} selected contact${ids.length === 1 ? '' : 's'}?`)) return
        await contactsApi.bulkDelete(ids)
      } else {
        return
      }
      clearSelection()
      await load()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const firstRow = total === 0 ? 0 : (page - 1) * pageSize + 1
  const lastRow = Math.min(page * pageSize, total)
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const hasFilters = Object.keys(filterParams).length > 0

  return (
    <div className="page">
      <div className="contacts-head">
        <div>
          <h1 className="page-title">Contacts</h1>
          <p className="page-subtitle">
            Phone and username leads, CSV/Excel import with dedupe, consent tracking, and Telegram resolution.
          </p>
        </div>
        <div className="contacts-head-actions">
          <ExportMenu onExport={runExport} hasSelection={selected.size > 0} />
        </div>
      </div>

      {error && <p className="form-error">{error}</p>}

      <ImportCard fileRef={fileRef} onImport={onImport} result={importResult} onError={setError} />
      <AddContactCard onCreated={load} onError={setError} />

      <section className="card">
        <div className="contacts-filters">
          <input
            className="c-search"
            placeholder="Search name / @username / phone / source"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select value={stageFilter} onChange={(e) => setStageFilter(e.target.value)}>
            <option value="">All stages</option>
            {CONTACT_STAGES.map((s) => (
              <option key={s} value={s}>
                {s.replace('_', ' ')}
              </option>
            ))}
          </select>
          <select value={leadTypeFilter} onChange={(e) => setLeadTypeFilter(e.target.value)}>
            <option value="">All types</option>
            <option value="username">username</option>
            <option value="phone">phone</option>
          </select>
          <select value={resolutionFilter} onChange={(e) => setResolutionFilter(e.target.value)}>
            <option value="">All resolution</option>
            <option value="pending">pending</option>
            <option value="resolved">resolved</option>
            <option value="no_telegram">no telegram</option>
            <option value="failed">failed</option>
          </select>
          <select value={consentFilter} onChange={(e) => setConsentFilter(e.target.value)}>
            <option value="">Any consent</option>
            <option value="true">consented</option>
            <option value="false">not consented</option>
          </select>
          <input
            className="c-source"
            list="contact-sources"
            placeholder="Source…"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
          />
          <datalist id="contact-sources">
            {sourceOptions.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
          {hasFilters && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setQ('')
                setStageFilter('')
                setLeadTypeFilter('')
                setResolutionFilter('')
                setConsentFilter('')
                setSourceFilter('')
              }}
            >
              Clear filters
            </button>
          )}
        </div>

        {selected.size > 0 && (
          <div className="bulk-bar">
            <span className="bulk-count">
              {selected.size} Contact{selected.size === 1 ? '' : 's'} Selected
            </span>
            <select
              className="bulk-actions"
              defaultValue=""
              onChange={(e) => {
                const v = e.target.value
                e.target.value = ''
                if (v) void runBulk(v)
              }}
            >
              <option value="">Bulk actions…</option>
              <optgroup label="Change stage">
                {CONTACT_STAGES.map((s) => (
                  <option key={s} value={`stage:${s}`}>
                    → {s.replace('_', ' ')}
                  </option>
                ))}
              </optgroup>
              <optgroup label="Consent">
                <option value="consent:on">Mark consent</option>
                <option value="consent:off">Remove consent</option>
              </optgroup>
              <optgroup label="Resolution">
                <option value="resolve">Resolve contacts</option>
                <option value="unresolve">Unresolve contacts</option>
              </optgroup>
              <optgroup label="Export">
                <option value="export:csv">Export selected (CSV)</option>
                <option value="export:xlsx">Export selected (Excel)</option>
              </optgroup>
              <optgroup label="Danger">
                <option value="delete">Delete selected…</option>
              </optgroup>
            </select>
            {allPageSelected && selected.size < total && (
              <button className="btn btn-ghost btn-sm" onClick={selectAllMatching}>
                Select all {total} matching
              </button>
            )}
            <button className="btn btn-ghost btn-sm" onClick={clearSelection}>
              Clear selection
            </button>
          </div>
        )}

        {loading ? (
          <ContactsSkeleton rows={Math.min(pageSize, 8)} />
        ) : contacts.length === 0 ? (
          <EmptyState hasFilters={hasFilters} />
        ) : (
          <div className="table-wrap">
            <table className="table contacts-table">
              <thead>
                <tr>
                  <th className="col-check">
                    <input
                      type="checkbox"
                      checked={allPageSelected}
                      onChange={togglePage}
                      title="Select current page"
                    />
                  </th>
                  <th>Contact</th>
                  <th>Type</th>
                  <th>Stage</th>
                  <th>Resolution</th>
                  <th>Consent</th>
                  <th>Source</th>
                  <th>Created</th>
                  <th className="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {contacts.map((c) => (
                  <tr
                    key={c.id}
                    className={selected.has(c.id) ? 'row-selected' : ''}
                    onDoubleClick={() => setEditFor(c)}
                  >
                    <td className="col-check">
                      <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)} />
                    </td>
                    <td>
                      <div className="contact-cell">
                        <Avatar c={c} />
                        <div className="contact-lines">
                          {c.name && <span className="contact-name">{c.name}</span>}
                          {c.username && <span className="contact-user">@{c.username}</span>}
                          {c.phone && <span className="contact-phone">{c.phone}</span>}
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="badge badge--muted">{c.lead_type}</span>
                    </td>
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
                    <td>{c.consent ? <span className="consent-yes">✓</span> : <span className="consent-no">—</span>}</td>
                    <td>{c.source || '—'}</td>
                    <td className="col-date">{new Date(c.created_at).toLocaleDateString()}</td>
                    <td className="col-actions">
                      <div className="quick-actions">
                        <button
                          className="icon-btn"
                          title={!c.consent || c.opted_out ? 'Cannot message (no consent / opted out)' : 'Message'}
                          onClick={() => setMessageFor(c)}
                          disabled={!c.consent || c.opted_out}
                        >
                          💬
                        </button>
                        <button className="icon-btn" title="Resolve on Telegram" onClick={() => resolveOne(c)}>
                          🔄
                        </button>
                        <button className="icon-btn" title="Edit" onClick={() => setEditFor(c)}>
                          ✏️
                        </button>
                        <button className="icon-btn icon-btn--danger" title="Delete" onClick={() => deleteOne(c)}>
                          🗑️
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && total > 0 && (
          <div className="pagination">
            <div className="pagination-info">
              Showing {firstRow.toLocaleString()}–{lastRow.toLocaleString()} of {total.toLocaleString()} contacts
            </div>
            <div className="pagination-controls">
              <label className="rows-per-page">
                Rows
                <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>
                  {PAGE_SIZES.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                ‹ Prev
              </button>
              <span className="page-indicator">
                {page} / {totalPages}
              </span>
              <button
                className="btn btn-ghost btn-sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next ›
              </button>
            </div>
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
      {editFor && (
        <ContactEditModal
          contact={editFor}
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

function ExportMenu({
  onExport,
  hasSelection,
}: {
  onExport: (format: 'csv' | 'xlsx', scope: 'all' | 'filtered' | 'selected') => void
  hasSelection: boolean
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])
  const pick = (format: 'csv' | 'xlsx', scope: 'all' | 'filtered' | 'selected') => {
    setOpen(false)
    onExport(format, scope)
  }
  return (
    <div className="export-menu" ref={ref}>
      <button className="btn btn-ghost" onClick={() => setOpen((o) => !o)}>
        Export ▾
      </button>
      {open && (
        <div className="export-dropdown">
          <button onClick={() => pick('csv', 'all')}>All contacts · CSV</button>
          <button onClick={() => pick('xlsx', 'all')}>All contacts · Excel</button>
          <button onClick={() => pick('csv', 'filtered')}>Filtered · CSV</button>
          <button onClick={() => pick('xlsx', 'filtered')}>Filtered · Excel</button>
          {hasSelection && (
            <>
              <button onClick={() => pick('csv', 'selected')}>Selected · CSV</button>
              <button onClick={() => pick('xlsx', 'selected')}>Selected · Excel</button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function ContactsSkeleton({ rows }: { rows: number }) {
  return (
    <div className="table-wrap">
      <table className="table contacts-table">
        <tbody>
          {Array.from({ length: rows }).map((_, i) => (
            <tr key={i}>
              <td className="col-check">
                <span className="skeleton skeleton-check" />
              </td>
              <td>
                <div className="contact-cell">
                  <span className="skeleton skeleton-avatar" />
                  <div className="contact-lines">
                    <span className="skeleton skeleton-line" />
                    <span className="skeleton skeleton-line short" />
                  </div>
                </div>
              </td>
              <td colSpan={7}>
                <span className="skeleton skeleton-line" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EmptyState({ hasFilters }: { hasFilters: boolean }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">👤</div>
      <h3>No contacts found</h3>
      <p>
        {hasFilters
          ? 'No contacts match the current filters. Try clearing them.'
          : 'Import contacts or add your first contact using the cards above.'}
      </p>
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
        <div className="import-summary">
          <span className="chip chip-ok">Imported {result.imported}</span>
          <span className="chip chip-info">Updated {result.updated}</span>
          <span className="chip">No consent {result.rejected_no_consent}</span>
          <span className="chip">Invalid {result.invalid}</span>
          {result.errors > 0 && <span className="chip chip-err">Errors {result.errors}</span>}
          <span className="chip chip-muted">Total {result.total}</span>
        </div>
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
