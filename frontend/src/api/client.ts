import { useAuth, type Role, type User } from '../store/auth'
import type { Theme } from '../lib/theme'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function apiFetch<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const { accessToken } = useAuth.getState()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) ?? {}),
  }
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`

  const res = await fetch(`/api${path}`, { ...options, headers })

  if (res.status === 401 && retry) {
    const refreshed = await useAuth.getState().refresh()
    if (refreshed) return apiFetch<T>(path, options, false)
    useAuth.getState().logout()
  }

  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export interface CreateStaffInput {
  email: string
  password: string
  full_name?: string | null
  role: Role
}

export interface UpdateStaffInput {
  full_name?: string | null
  role?: Role
  is_active?: boolean
  password?: string
}

export interface AuditEvent {
  id: number
  type: string
  actor_type: string
  actor_id: number | null
  entity_ref: string | null
  meta: Record<string, unknown>
  created_at: string
}

export const staffApi = {
  list: () => apiFetch<User[]>('/users'),
  create: (data: CreateStaffInput) =>
    apiFetch<User>('/users', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: UpdateStaffInput) =>
    apiFetch<User>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deactivate: (id: number) => apiFetch<User>(`/users/${id}`, { method: 'DELETE' }),
}

export const meApi = {
  update: (data: { full_name?: string | null; theme?: Theme; password?: string }) =>
    apiFetch<User>('/auth/me', { method: 'PATCH', body: JSON.stringify(data) }),
}

export const auditApi = {
  list: () => apiFetch<AuditEvent[]>('/audit'),
}

// ---- Accounts & proxies (Phase 2) ----

export interface Account {
  id: number
  label: string
  phone: string | null
  api_id: string | null
  session_ref: string | null
  proxy_id: number | null
  status: string
  warmup_stage: number
  daily_cap: number
  actions_today: number
  last_action_at: string | null
  spam_state: string
  created_at: string
}

export interface AccountStatus {
  id: number
  label: string
  status: string
  connected: boolean
  authorized: boolean
  telegram_user: Record<string, unknown> | null
  engine_reachable: boolean
  detail: string | null
}

export interface CreateAccountInput {
  label: string
  phone?: string | null
  api_id?: string | null
  api_hash?: string | null
  assign_proxy: boolean
}

export interface Proxy {
  id: number
  type: string
  host: string
  port: number
  username: string | null
  is_active: boolean
  assigned_account_id: number | null
  health: string
  last_checked_at: string | null
  notes: string | null
  created_at: string
}

export interface ProxyImportResult {
  imported: number
  skipped_duplicates: number
  invalid: string[]
  total_in_pool: number
}

export interface QrStatus {
  status: 'waiting' | 'password_needed' | 'authorized' | 'expired' | 'error'
  url: string | null
  telegram_user: Record<string, unknown> | null
  detail: string | null
}

export interface LoginResult {
  status: 'authorized' | 'password_needed' | 'error'
  telegram_user: Record<string, unknown> | null
  detail: string | null
}

export const accountsApi = {
  list: () => apiFetch<Account[]>('/accounts'),
  create: (data: CreateAccountInput) =>
    apiFetch<Account>('/accounts', { method: 'POST', body: JSON.stringify(data) }),
  remove: (id: number) => apiFetch<void>(`/accounts/${id}`, { method: 'DELETE' }),
  status: (id: number) => apiFetch<AccountStatus>(`/accounts/${id}/status`),
  logout: (id: number) => apiFetch<Account>(`/accounts/${id}/logout`, { method: 'POST' }),
  qrStart: (id: number) =>
    apiFetch<{ url: string }>(`/accounts/${id}/login/qr`, { method: 'POST' }),
  qrStatus: (id: number) => apiFetch<QrStatus>(`/accounts/${id}/login/qr`),
  qrPassword: (id: number, password: string) =>
    apiFetch<LoginResult>(`/accounts/${id}/login/qr/password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  phoneSendCode: (id: number, phone: string) =>
    apiFetch<{ phone_code_hash: string }>(`/accounts/${id}/login/phone/send-code`, {
      method: 'POST',
      body: JSON.stringify({ phone }),
    }),
  phoneSignIn: (
    id: number,
    body: { phone: string; code: string; phone_code_hash: string; password?: string },
  ) =>
    apiFetch<LoginResult>(`/accounts/${id}/login/phone/sign-in`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  importSession: (id: number, session_string: string) =>
    apiFetch<LoginResult>(`/accounts/${id}/login/session`, {
      method: 'POST',
      body: JSON.stringify({ session_string }),
    }),
}

export const proxiesApi = {
  list: () => apiFetch<Proxy[]>('/proxies'),
  import: (raw: string) =>
    apiFetch<ProxyImportResult>('/proxies/import', {
      method: 'POST',
      body: JSON.stringify({ raw }),
    }),
}
