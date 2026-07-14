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

export type AccountStatusValue =
  | 'active'
  | 'warming'
  | 'quarantined'
  | 'banned'
  | 'logged_out'

export interface SpamCheckResult {
  spam_state: string
  reply: string | null
  quarantined: boolean
  detail: string | null
}

export interface BanCheckResult {
  state: string
  telegram_user: Record<string, unknown> | null
  status: string
  detail: string | null
}

export interface AppealResult {
  submitted: boolean
  reply: string | null
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
  setStatus: (id: number, status: AccountStatusValue) =>
    apiFetch<Account>(`/accounts/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  spamCheck: (id: number) =>
    apiFetch<SpamCheckResult>(`/accounts/${id}/health/spam-check`, { method: 'POST' }),
  banCheck: (id: number) =>
    apiFetch<BanCheckResult>(`/accounts/${id}/health/ban-check`, { method: 'POST' }),
  unspam: (id: number) =>
    apiFetch<AppealResult>(`/accounts/${id}/health/unspam`, { method: 'POST' }),
  unfreeze: (id: number) =>
    apiFetch<AppealResult>(`/accounts/${id}/health/unfreeze`, { method: 'POST' }),
}

export const proxiesApi = {
  list: () => apiFetch<Proxy[]>('/proxies'),
  import: (raw: string) =>
    apiFetch<ProxyImportResult>('/proxies/import', {
      method: 'POST',
      body: JSON.stringify({ raw }),
    }),
}

// ---- Warmup (Phase 4) ----

export interface WarmupStage {
  days: number
  max_actions: number
}

export interface WarmupRun {
  id: number
  name: string
  status: string
  stages: WarmupStage[]
  groups: string[]
  messages: string[]
  min_delay_seconds: number
  max_delay_seconds: number
  created_at: string
  started_at: string | null
}

export interface WarmupParticipant {
  id: number
  account_id: number
  account_label: string
  stage: number
  stage_progress: string
  actions_today: number
  status: string
  last_action_at: string | null
  joined: string[]
}

export interface WarmupPartner {
  id: number
  identifier: string
  kind: 'phone' | 'username'
}

export interface WarmupRunDetail extends WarmupRun {
  participants: WarmupParticipant[]
  partners: WarmupPartner[]
}

export interface TickResult {
  advanced: number
  completed: number
  actions: Array<Record<string, unknown>>
  errors: Array<Record<string, unknown>>
}

export interface CreateRunInput {
  name: string
  groups: string[]
  messages: string[]
  stages?: WarmupStage[]
  min_delay_seconds?: number
  max_delay_seconds?: number
}

// ---- Contacts (Phase 5) ----

export type ContactStage =
  | 'new'
  | 'contacted'
  | 'replied'
  | 'joined'
  | 'customer'
  | 'opted_out'

export const CONTACT_STAGES: ContactStage[] = [
  'new',
  'contacted',
  'replied',
  'joined',
  'customer',
  'opted_out',
]

export interface Contact {
  id: number
  name: string | null
  display_label: string
  lead_type: 'phone' | 'username'
  phone: string | null
  username: string | null
  telegram_user_id: number | null
  resolution_status: string
  source: string | null
  stage: ContactStage
  consent: boolean
  opted_out: boolean
  assigned_account_id: number | null
  assigned_agent_id: number | null
  utm: Record<string, unknown>
  tags: string[]
  created_at: string
  last_contacted_at: string | null
}

export interface ContactImportResult {
  imported: number
  skipped_duplicates: number
  rejected_no_consent: number
  invalid: number
  total: number
}

export interface CreateContactInput {
  name?: string | null
  phone?: string | null
  username?: string | null
  source?: string | null
  consent: boolean
  tags?: string[]
}

async function multipartUpload<T>(path: string, file: File): Promise<T> {
  const { accessToken } = useAuth.getState()
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    body: form,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const b = await res.json()
      if (b?.detail) detail = typeof b.detail === 'string' ? b.detail : JSON.stringify(b.detail)
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export const contactsApi = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString()
    return apiFetch<Contact[]>(`/contacts${qs ? `?${qs}` : ''}`)
  },
  create: (data: CreateContactInput) =>
    apiFetch<Contact>('/contacts', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: Partial<Contact>) =>
    apiFetch<Contact>(`/contacts/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  remove: (id: number) => apiFetch<void>(`/contacts/${id}`, { method: 'DELETE' }),
  importFile: (file: File) => multipartUpload<ContactImportResult>('/contacts/import', file),
  resolveOne: (id: number) =>
    apiFetch<{ id: number; resolution_status: string; telegram_user_id: number | null }>(
      `/contacts/${id}/resolve`,
      { method: 'POST' },
    ),
  message: (id: number, account_id: number, text: string) =>
    apiFetch<Contact>(`/contacts/${id}/message`, {
      method: 'POST',
      body: JSON.stringify({ account_id, text }),
    }),
  bulkStage: (contact_ids: number[], stage: ContactStage) =>
    apiFetch<number>('/contacts/bulk/stage', {
      method: 'POST',
      body: JSON.stringify({ contact_ids, stage }),
    }),
  bulkDelete: (contact_ids: number[]) =>
    apiFetch<number>('/contacts/bulk/delete', {
      method: 'POST',
      body: JSON.stringify({ contact_ids }),
    }),
  downloadTemplate: async () => {
    const { accessToken } = useAuth.getState()
    const res = await fetch('/api/contacts/import-template', {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'contacts_template.csv'
    a.click()
    URL.revokeObjectURL(url)
  },
}

export const warmupApi = {
  listRuns: () => apiFetch<WarmupRun[]>('/warmup/runs'),
  createRun: (data: CreateRunInput) =>
    apiFetch<WarmupRun>('/warmup/runs', { method: 'POST', body: JSON.stringify(data) }),
  getRun: (id: number) => apiFetch<WarmupRunDetail>(`/warmup/runs/${id}`),
  deleteRun: (id: number) =>
    apiFetch<void>(`/warmup/runs/${id}`, { method: 'DELETE' }),
  addParticipants: (id: number, account_ids: number[]) =>
    apiFetch<WarmupRunDetail>(`/warmup/runs/${id}/participants`, {
      method: 'POST',
      body: JSON.stringify({ account_ids }),
    }),
  removeParticipant: (id: number, pid: number) =>
    apiFetch<WarmupRunDetail>(`/warmup/runs/${id}/participants/${pid}`, {
      method: 'DELETE',
    }),
  addPartner: (id: number, identifier: string, kind: 'phone' | 'username') =>
    apiFetch<WarmupRunDetail>(`/warmup/runs/${id}/partners`, {
      method: 'POST',
      body: JSON.stringify({ identifier, kind }),
    }),
  start: (id: number) =>
    apiFetch<WarmupRunDetail>(`/warmup/runs/${id}/start`, { method: 'POST' }),
  pause: (id: number) =>
    apiFetch<WarmupRunDetail>(`/warmup/runs/${id}/pause`, { method: 'POST' }),
  stop: (id: number) =>
    apiFetch<WarmupRunDetail>(`/warmup/runs/${id}/stop`, { method: 'POST' }),
  tick: (id: number) =>
    apiFetch<TickResult>(`/warmup/runs/${id}/tick`, { method: 'POST' }),
}
