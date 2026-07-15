import { useEffect, useState, type FormEvent } from 'react'
import {
  ApiError,
  campaignsApi,
  destinationsApi,
  templatesApi,
  type Campaign,
  type CampaignDetail,
  type Destination,
  type Template,
} from '../api/client'

const CAMPAIGN_BADGE: Record<string, string> = {
  draft: 'badge--muted',
  running: 'badge--ok',
  paused: 'badge--wait',
  done: 'badge--muted',
}

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

export default function Campaigns() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [destinations, setDestinations] = useState<Destination[]>([])
  const [selected, setSelected] = useState<CampaignDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const loadAll = async () => {
    try {
      setTemplates(await templatesApi.list())
      setCampaigns(await campaignsApi.list())
      setDestinations(await destinationsApi.list())
    } catch (e) {
      setError(errMsg(e))
    }
  }

  useEffect(() => {
    void loadAll()
  }, [])

  const open = async (id: number) => {
    setNote(null)
    try {
      setSelected(await campaignsApi.get(id))
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const refresh = async () => {
    if (selected) setSelected(await campaignsApi.get(selected.id))
  }

  const control = async (fn: () => Promise<CampaignDetail>) => {
    setError(null)
    try {
      setSelected(await fn())
      await loadAll()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const runTick = async () => {
    if (!selected) return
    setError(null)
    setNote(null)
    try {
      const r = await campaignsApi.tick(selected.id)
      setNote(
        `Tick: ${r.sent} sent, ${r.joined} joined, ${r.failed} failed` +
          (r.paused ? ` — auto-paused (${r.warning})` : ''),
      )
      await refresh()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const variantGroups = [...new Set(templates.map((t) => t.variant_group))]

  return (
    <div className="page">
      <h1 className="page-title">Campaigns</h1>
      <p className="page-subtitle">
        Segmented, scheduled multi-step campaigns with spintax templates, A/B variants, and
        message / add actions.
      </p>

      {error && <p className="form-error">{error}</p>}

      <TemplatesCard templates={templates} onCreated={loadAll} onError={setError} />

      <div className="warmup-grid">
        <div>
          <CreateCampaignCard
            variantGroups={variantGroups}
            destinations={destinations}
            onCreated={loadAll}
            onError={setError}
          />
          <section className="card">
            <div className="card-head">Campaigns</div>
            {campaigns.length === 0 ? (
              <p className="hint">No campaigns yet.</p>
            ) : (
              <ul className="run-list">
                {campaigns.map((c) => (
                  <li
                    key={c.id}
                    className={`run-item${selected?.id === c.id ? ' run-item--active' : ''}`}
                    onClick={() => open(c.id)}
                  >
                    <span>{c.name}</span>
                    <span className={`badge ${CAMPAIGN_BADGE[c.status] ?? 'badge--muted'}`}>
                      {c.status}
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
              <p className="hint">Select a campaign to view A/B results and launch it.</p>
            </section>
          ) : (
            <CampaignDetailView
              campaign={selected}
              note={note}
              onControl={control}
              onTick={runTick}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function TemplatesCard({
  templates,
  onCreated,
  onError,
}: {
  templates: Template[]
  onCreated: () => void
  onError: (m: string) => void
}) {
  const [name, setName] = useState('')
  const [body, setBody] = useState('')
  const [group, setGroup] = useState('')
  const [label, setLabel] = useState('A')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await templatesApi.create({ name, body, variant_group: group, variant_label: label })
      setName('')
      setBody('')
      onCreated()
    } catch (err) {
      onError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <div className="card-head">Templates (spintax + A/B variants)</div>
      <form className="form-row" onSubmit={submit}>
        <input placeholder="Template name" required value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="Variant group (A/B key)" required value={group} onChange={(e) => setGroup(e.target.value)} />
        <input placeholder="Label (A/B)" value={label} onChange={(e) => setLabel(e.target.value)} style={{ maxWidth: 90 }} />
        <button className="btn btn-primary" type="submit" disabled={busy || !name || !body || !group}>
          Add
        </button>
      </form>
      <textarea
        className="textarea"
        rows={2}
        placeholder={'Body with spintax, e.g. {Hi|Hello} there!'}
        value={body}
        onChange={(e) => setBody(e.target.value)}
      />
      {templates.length > 0 && (
        <ul className="chip-list">
          {templates.map((t) => (
            <li key={t.id} className="chip">
              {t.variant_group} · {t.variant_label} <small>({t.name})</small>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function CreateCampaignCard({
  variantGroups,
  destinations,
  onCreated,
  onError,
}: {
  variantGroups: string[]
  destinations: Destination[]
  onCreated: () => void
  onError: (m: string) => void
}) {
  const [name, setName] = useState('')
  const [action, setAction] = useState('message')
  const [source, setSource] = useState('')
  const [variantGroup, setVariantGroup] = useState('')
  const [abTest, setAbTest] = useState(false)
  const [destinationId, setDestinationId] = useState('')
  const [excludeDest, setExcludeDest] = useState('')
  const [offsets, setOffsets] = useState('0')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const steps = offsets
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .map((h) => ({
          offset_hours: Number(h) || 0,
          variant_group: action === 'message' ? variantGroup : null,
        }))
      const segment: Record<string, unknown> = {}
      if (source) segment.source = source
      if (excludeDest) segment.exclude_in_destination = Number(excludeDest)
      await campaignsApi.create({
        name,
        action,
        destination_id: action !== 'message' && destinationId ? Number(destinationId) : null,
        segment,
        steps: steps.length ? steps : [{ offset_hours: 0, variant_group: variantGroup || null }],
        ab_test: abTest,
      })
      setName('')
      onCreated()
    } catch (err) {
      onError(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <div className="card-head">New campaign</div>
      <form className="field-block" onSubmit={submit}>
        <input placeholder="Campaign name" required value={name} onChange={(e) => setName(e.target.value)} />
        <div className="form-row">
          <select value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="message">message</option>
            <option value="add">add to group</option>
          </select>
          <input placeholder="Segment source (optional)" value={source} onChange={(e) => setSource(e.target.value)} />
        </div>
        {action === 'message' ? (
          <div className="form-row">
            <select value={variantGroup} onChange={(e) => setVariantGroup(e.target.value)} required>
              <option value="">Template variant group…</option>
              {variantGroups.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
            <label className="checkbox">
              <input type="checkbox" checked={abTest} onChange={(e) => setAbTest(e.target.checked)} />
              <span>A/B test</span>
            </label>
          </div>
        ) : (
          <select value={destinationId} onChange={(e) => setDestinationId(e.target.value)} required>
            <option value="">Destination…</option>
            {destinations.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title || d.link}
              </option>
            ))}
          </select>
        )}
        <div className="form-row">
          <input placeholder="Drip offsets in hours (e.g. 0,24)" value={offsets} onChange={(e) => setOffsets(e.target.value)} />
          <select value={excludeDest} onChange={(e) => setExcludeDest(e.target.value)}>
            <option value="">Exclude already-in group…</option>
            {destinations.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title || d.link}
              </option>
            ))}
          </select>
        </div>
        <button className="btn btn-primary" type="submit" disabled={busy || !name}>
          Create campaign
        </button>
      </form>
    </section>
  )
}

function CampaignDetailView({
  campaign,
  note,
  onControl,
  onTick,
}: {
  campaign: CampaignDetail
  note: string | null
  onControl: (fn: () => Promise<CampaignDetail>) => void
  onTick: () => void
}) {
  const s = campaign.stats
  return (
    <>
      <section className="card">
        <div className="run-detail-head">
          <div>
            <h2 className="run-title">{campaign.name}</h2>
            <span className={`badge ${CAMPAIGN_BADGE[campaign.status] ?? 'badge--muted'}`}>
              {campaign.status}
            </span>{' '}
            <span className="hint-inline">
              {campaign.action}
              {campaign.ab_test ? ' · A/B' : ''}
            </span>
          </div>
          <div className="run-controls">
            {campaign.status === 'draft' && (
              <button className="btn btn-primary btn-sm" onClick={() => onControl(() => campaignsApi.start(campaign.id))}>
                Start
              </button>
            )}
            {campaign.status === 'running' && (
              <>
                <button className="btn btn-ghost btn-sm" onClick={onTick}>
                  Run tick
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => onControl(() => campaignsApi.pause(campaign.id))}>
                  Pause
                </button>
              </>
            )}
            {campaign.status === 'paused' && (
              <button className="btn btn-primary btn-sm" onClick={() => onControl(() => campaignsApi.start(campaign.id))}>
                Resume
              </button>
            )}
            {campaign.status !== 'done' && (
              <button className="btn btn-ghost btn-sm" onClick={() => onControl(() => campaignsApi.stop(campaign.id))}>
                Stop
              </button>
            )}
          </div>
        </div>
        {note && <p className="hint">{note}</p>}
        <p className="hint">
          queued {s.queued ?? 0} · sent {s.sent ?? 0} · joined {s.joined ?? 0} · failed{' '}
          {s.failed ?? 0}
        </p>
      </section>

      <section className="card">
        <div className="card-head">A/B results</div>
        {campaign.ab_report.length === 0 ? (
          <p className="hint">No results yet — start the campaign and run a tick.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Variant</th>
                  <th>Template</th>
                  <th>Sent</th>
                  <th>Joined</th>
                  <th>Replied</th>
                  <th>Failed</th>
                </tr>
              </thead>
              <tbody>
                {campaign.ab_report.map((r) => (
                  <tr key={r.template_id ?? 'none'}>
                    <td>
                      <span className="badge badge--muted">{r.label}</span>
                    </td>
                    <td>{r.name}</td>
                    <td>{r.sent}</td>
                    <td>{r.joined}</td>
                    <td>{r.replied}</td>
                    <td>{r.failed}</td>
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
