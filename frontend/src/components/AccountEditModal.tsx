import { useState } from 'react'
import { ApiError, accountsApi, type Account, type Proxy, type UpdateAccountInput } from '../api/client'

/** The single unified Edit modal for a Telegram account (§15.6):
 *  account name, its real Telegram identity (read-only), and proxy
 *  enable/disable + selection. Login, session, health and spam are untouched. */
export default function AccountEditModal({
  account,
  proxies,
  onClose,
  onSaved,
}: {
  account: Account
  proxies: Proxy[]
  onClose: () => void
  onSaved: () => void
}) {
  const [label, setLabel] = useState(account.label)
  const [useProxy, setUseProxy] = useState(account.proxy_id !== null)
  const [proxyId, setProxyId] = useState<string>(
    account.proxy_id !== null ? String(account.proxy_id) : '',
  )
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Selectable proxies: the free ones plus whichever this account already holds.
  const selectable = proxies.filter(
    (p) => p.assigned_account_id === null || p.assigned_account_id === account.id,
  )

  const save = async () => {
    setError(null)
    setSuccess(null)
    if (!label.trim()) {
      setError('Account name cannot be empty.')
      return
    }
    const payload: UpdateAccountInput = { label: label.trim(), assign_proxy: useProxy }
    if (useProxy && proxyId) payload.proxy_id = Number(proxyId)
    setBusy(true)
    try {
      await accountsApi.update(account.id, payload)
      setSuccess('Account updated successfully.')
      onSaved()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to update account')
    } finally {
      setBusy(false)
    }
  }

  const hasIdentity = account.tg_username || account.tg_user_id || account.phone

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Edit account</h2>
          <button className="icon-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {error && <p className="form-error">{error}</p>}
        {success && <p className="form-success">{success}</p>}

        <div className="field-block">
          <span className="label">Account name</span>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Sales 1"
          />
          <p className="hint">Your own label for this account — it is not your Telegram name.</p>
        </div>

        <div className="field-block">
          <span className="label">Telegram identity</span>
          <div className="tg-identity">
            {hasIdentity ? (
              <>
                {account.tg_first_name && (
                  <div className="tg-identity-name">{account.tg_first_name}</div>
                )}
                {account.tg_username ? (
                  <div className="tg-identity-row">@{account.tg_username}</div>
                ) : (
                  <div className="tg-identity-row tg-identity-muted">no username set</div>
                )}
                {account.phone && <div className="tg-identity-row">{account.phone}</div>}
                {account.tg_user_id && (
                  <div className="tg-identity-row tg-identity-muted">ID {account.tg_user_id}</div>
                )}
              </>
            ) : (
              <div className="tg-identity-muted">
                Unknown — log this account in (or run a status check) to read its Telegram identity.
              </div>
            )}
          </div>
        </div>

        <div className="field-block">
          <span className="label">Proxy</span>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={useProxy}
              onChange={(e) => {
                setUseProxy(e.target.checked)
                if (!e.target.checked) setProxyId('')
              }}
            />
            <span>Assign proxy</span>
          </label>
          {useProxy && (
            <>
              <select value={proxyId} onChange={(e) => setProxyId(e.target.value)}>
                <option value="">Auto-assign a free proxy</option>
                {selectable.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.type}://{p.host}:{p.port}
                    {p.assigned_account_id === account.id ? ' (current)' : ''}
                    {p.health !== 'ok' ? ` · ${p.health}` : ''}
                  </option>
                ))}
              </select>
              {selectable.length === 0 && (
                <p className="hint">No free proxies in the pool — import some first.</p>
              )}
            </>
          )}
          {!useProxy && account.proxy_id !== null && (
            <p className="hint">Saving will release this account's proxy back to the pool.</p>
          )}
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
