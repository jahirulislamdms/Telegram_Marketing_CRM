import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../store/auth'

interface LocationState {
  from?: string
}

export default function Login() {
  const login = useAuth((s) => s.login)
  const status = useAuth((s) => s.status)
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const from = (location.state as LocationState | null)?.from ?? '/'

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    }
  }

  return (
    <div className="auth-shell">
      <form className="auth-card" onSubmit={onSubmit}>
        <div className="auth-brand">Telegram Marketing CRM</div>
        <h1 className="auth-title">Sign in</h1>

        <label className="field">
          <span>Email</span>
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            placeholder="you@company.com"
          />
        </label>

        <label className="field">
          <span>Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            placeholder="••••••••"
          />
        </label>

        {error && <p className="form-error">{error}</p>}

        <button className="btn btn-primary btn-block" type="submit" disabled={status === 'loading'}>
          {status === 'loading' ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
