import { useEffect, useRef, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { ApiError, accountsApi, type Account } from '../api/client'

type Method = 'choose' | 'qr' | 'phone' | 'session'

interface Props {
  account: Account
  onClose: () => void
  onSuccess: () => void
}

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  return e instanceof Error ? e.message : 'Something went wrong'
}

export default function AccountLoginModal({ account, onClose, onSuccess }: Props) {
  const [method, setMethod] = useState<Method>('choose')

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Log in — {account.label}</h2>
          <button className="icon-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {method === 'choose' && (
          <div className="method-grid">
            <button className="method-card" onClick={() => setMethod('qr')}>
              <span className="method-icon">▦</span>
              <span>QR code</span>
              <small>Scan from Telegram app</small>
            </button>
            <button className="method-card" onClick={() => setMethod('phone')}>
              <span className="method-icon">☏</span>
              <span>Phone number</span>
              <small>Code sent to Telegram</small>
            </button>
            <button className="method-card" onClick={() => setMethod('session')}>
              <span className="method-icon">⇩</span>
              <span>Session string</span>
              <small>Import existing session</small>
            </button>
          </div>
        )}

        {method === 'qr' && (
          <QrLogin account={account} onSuccess={onSuccess} onBack={() => setMethod('choose')} />
        )}
        {method === 'phone' && (
          <PhoneLogin account={account} onSuccess={onSuccess} onBack={() => setMethod('choose')} />
        )}
        {method === 'session' && (
          <SessionLogin account={account} onSuccess={onSuccess} onBack={() => setMethod('choose')} />
        )}
      </div>
    </div>
  )
}

interface FlowProps {
  account: Account
  onSuccess: () => void
  onBack: () => void
}

function QrLogin({ account, onSuccess, onBack }: FlowProps) {
  const [url, setUrl] = useState<string | null>(null)
  const [state, setState] = useState<string>('loading')
  const [error, setError] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const timer = useRef<number | null>(null)

  useEffect(() => {
    let active = true
    const stop = () => {
      if (timer.current) window.clearInterval(timer.current)
    }
    accountsApi
      .qrStart(account.id)
      .then((r) => {
        if (!active) return
        setUrl(r.url)
        setState('waiting')
        timer.current = window.setInterval(async () => {
          try {
            const s = await accountsApi.qrStatus(account.id)
            if (!active) return
            setState(s.status)
            if (s.url) setUrl(s.url)
            if (s.status === 'authorized') {
              stop()
              onSuccess()
            } else if (s.status === 'password_needed' || s.status === 'expired') {
              stop()
            }
          } catch (e) {
            setError(errMsg(e))
            stop()
          }
        }, 2000)
      })
      .catch((e) => active && setError(errMsg(e)))
    return () => {
      active = false
      stop()
    }
  }, [account.id])

  const submitPassword = async () => {
    setError(null)
    try {
      const r = await accountsApi.qrPassword(account.id, password)
      if (r.status === 'authorized') onSuccess()
      else setError(r.detail || 'Incorrect password')
    } catch (e) {
      setError(errMsg(e))
    }
  }

  return (
    <div className="flow">
      {error && <p className="form-error">{error}</p>}
      {state === 'waiting' && url && (
        <div className="qr-wrap">
          <div className="qr-box">
            <QRCodeSVG value={url} size={200} includeMargin />
          </div>
          <p className="hint">Open Telegram → Settings → Devices → Link Desktop Device, then scan.</p>
        </div>
      )}
      {state === 'password_needed' && (
        <div className="field-block">
          <p className="hint">Two-step verification is enabled. Enter your password.</p>
          <input
            type="password"
            placeholder="2FA password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button className="btn btn-primary" onClick={submitPassword}>
            Submit
          </button>
        </div>
      )}
      {state === 'expired' && <p className="hint">QR code expired. Go back and try again.</p>}
      {state === 'loading' && !error && <p className="hint">Generating QR code…</p>}
      <button className="btn btn-ghost" onClick={onBack}>
        ← Back
      </button>
    </div>
  )
}

function PhoneLogin({ account, onSuccess, onBack }: FlowProps) {
  const [phone, setPhone] = useState(account.phone ?? '')
  const [hash, setHash] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [needPassword, setNeedPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const sendCode = async () => {
    setError(null)
    setBusy(true)
    try {
      const r = await accountsApi.phoneSendCode(account.id, phone)
      setHash(r.phone_code_hash)
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const signIn = async () => {
    if (!hash) return
    setError(null)
    setBusy(true)
    try {
      const r = await accountsApi.phoneSignIn(account.id, {
        phone,
        code,
        phone_code_hash: hash,
        password: needPassword ? password : undefined,
      })
      if (r.status === 'authorized') onSuccess()
      else if (r.status === 'password_needed') setNeedPassword(true)
      else setError(r.detail || 'Sign-in failed')
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flow">
      {error && <p className="form-error">{error}</p>}
      {!hash ? (
        <div className="field-block">
          <input
            type="tel"
            placeholder="+1234567890"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
          <button className="btn btn-primary" onClick={sendCode} disabled={busy || !phone}>
            {busy ? 'Sending…' : 'Send code'}
          </button>
        </div>
      ) : (
        <div className="field-block">
          <input
            type="text"
            placeholder="Login code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          {needPassword && (
            <input
              type="password"
              placeholder="2FA password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
          <button className="btn btn-primary" onClick={signIn} disabled={busy || !code}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </div>
      )}
      <button className="btn btn-ghost" onClick={onBack}>
        ← Back
      </button>
    </div>
  )
}

function SessionLogin({ account, onSuccess, onBack }: FlowProps) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setError(null)
    setBusy(true)
    try {
      const r = await accountsApi.importSession(account.id, value.trim())
      if (r.status === 'authorized') onSuccess()
      else setError(r.detail || 'Import failed')
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flow">
      {error && <p className="form-error">{error}</p>}
      <div className="field-block">
        <textarea
          className="textarea"
          placeholder="Paste a Telethon StringSession…"
          rows={4}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <button className="btn btn-primary" onClick={submit} disabled={busy || value.length < 10}>
          {busy ? 'Importing…' : 'Import session'}
        </button>
      </div>
      <button className="btn btn-ghost" onClick={onBack}>
        ← Back
      </button>
    </div>
  )
}
