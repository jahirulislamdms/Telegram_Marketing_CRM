import { useEffect, useState } from 'react'
import {
  ApiError,
  CONTACT_STAGES,
  contactsApi,
  type Contact,
  type ContactStage,
} from '../api/client'

const STAGE_TITLES: Record<ContactStage, string> = {
  new: 'New',
  contacted: 'Contacted',
  replied: 'Replied',
  joined: 'Joined',
  customer: 'Customer',
  opted_out: 'Opted out',
}

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

export default function Pipeline() {
  const [contacts, setContacts] = useState<Contact[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      setContacts(await contactsApi.list())
    } catch (e) {
      setError(errMsg(e))
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const move = async (c: Contact, stage: ContactStage) => {
    setError(null)
    try {
      await contactsApi.update(c.id, { stage })
      await load()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  const byStage = (s: ContactStage) => contacts.filter((c) => c.stage === s)

  return (
    <div className="page">
      <h1 className="page-title">Pipeline</h1>
      <p className="page-subtitle">Move contacts through the CRM stages.</p>
      {error && <p className="form-error">{error}</p>}

      <div className="kanban">
        {CONTACT_STAGES.map((stage) => (
          <div className="kanban-col" key={stage}>
            <div className="kanban-col-head">
              {STAGE_TITLES[stage]} <span className="hint-inline">{byStage(stage).length}</span>
            </div>
            <div className="kanban-cards">
              {byStage(stage).map((c) => (
                <div className="kanban-card" key={c.id}>
                  <div className="kanban-card-title">{c.display_label}</div>
                  <div className="kanban-card-meta">
                    {c.lead_type}
                    {c.source ? ` · ${c.source}` : ''}
                  </div>
                  <select
                    className="kanban-move"
                    value={c.stage}
                    onChange={(e) => move(c, e.target.value as ContactStage)}
                  >
                    {CONTACT_STAGES.map((s) => (
                      <option key={s} value={s}>
                        {STAGE_TITLES[s]}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
