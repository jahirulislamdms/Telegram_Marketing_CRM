import { useEffect, useState } from 'react'
import {
  ApiError,
  accountsApi,
  contactsApi,
  type Account,
  type Contact,
} from '../api/client'

interface Props {
  contact: Contact
  onClose: () => void
  onSent: () => void
}

export default function ContactMessageModal({ contact, onClose, onSent }: Props) {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [accountId, setAccountId] = useState('')
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    accountsApi
      .list()
      .then((list) => setAccounts(list.filter((a) => a.session_ref)))
      .catch(() => setAccounts([]))
  }, [])

  const send = async () => {
    setError(null)
    setBusy(true)
    try {
      await contactsApi.message(contact.id, Number(accountId), text)
      onSent()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to send')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Message {contact.display_label}</h2>
          <button className="icon-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {error && <p className="form-error">{error}</p>}

        <div className="field-block">
          <span className="label">Send from account</span>
          <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">Select a logged-in account…</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
          {accounts.length === 0 && (
            <p className="hint">No logged-in accounts available.</p>
          )}
          <textarea
            className="textarea"
            rows={4}
            placeholder="Your message…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button
            className="btn btn-primary"
            onClick={send}
            disabled={busy || !accountId || text.trim().length === 0}
          >
            {busy ? 'Sending…' : 'Send message'}
          </button>
        </div>
      </div>
    </div>
  )
}
