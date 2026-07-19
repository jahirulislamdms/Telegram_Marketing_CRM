import { useState } from 'react'
import {
  ApiError,
  CONTACT_STAGES,
  contactsApi,
  type Contact,
  type ContactStage,
} from '../api/client'

interface Props {
  contact: Contact
  onClose: () => void
  onSaved: (updated: Contact) => void
}

/** Edit Contact modal (§15.3 #3): name / phone / username / source / stage /
 * consent / notes. The stage list is the exact CRM pipeline set — unchanged. */
export default function ContactEditModal({ contact, onClose, onSaved }: Props) {
  const [name, setName] = useState(contact.name ?? '')
  const [phone, setPhone] = useState(contact.phone ?? '')
  const [username, setUsername] = useState(contact.username ? `@${contact.username}` : '')
  const [source, setSource] = useState(contact.source ?? '')
  const [stage, setStage] = useState<ContactStage>(contact.stage)
  const [consent, setConsent] = useState(contact.consent)
  const [notes, setNotes] = useState(contact.notes ?? '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const save = async () => {
    setError(null)
    setBusy(true)
    try {
      const updated = await contactsApi.update(contact.id, {
        name: name.trim() || null,
        phone: phone.trim() || null,
        username: username.trim() || null,
        source: source.trim() || null,
        notes: notes.trim() || null,
        stage,
        consent,
      } as Partial<Contact>)
      onSaved(updated)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to save')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Edit contact</h2>
          <button className="icon-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {error && <p className="form-error">{error}</p>}

        <div className="field-block">
          <span className="label">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" />
        </div>
        <div className="edit-grid">
          <div className="field-block">
            <span className="label">Phone</span>
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+15550001234" />
          </div>
          <div className="field-block">
            <span className="label">Username</span>
            <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="@username" />
          </div>
        </div>
        <div className="edit-grid">
          <div className="field-block">
            <span className="label">Source</span>
            <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="e.g. online_store" />
          </div>
          <div className="field-block">
            <span className="label">Stage</span>
            <select value={stage} onChange={(e) => setStage(e.target.value as ContactStage)}>
              {CONTACT_STAGES.map((s) => (
                <option key={s} value={s}>
                  {s.replace('_', ' ')}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="field-block">
          <label className="checkbox">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>Consent to be contacted</span>
          </label>
        </div>
        <div className="field-block">
          <span className="label">Notes</span>
          <textarea
            className="textarea"
            rows={3}
            placeholder="Internal notes (optional)…"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>

        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>
            {busy ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  )
}
