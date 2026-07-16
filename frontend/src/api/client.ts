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

// ---- Inbox (Phase 6) ----

export const CONVERSATION_STATUSES = [
  'new',
  'contacted',
  'replied',
  'joined',
  'customer',
  'opted_out',
  'blocked',
] as const

export type ConversationStatus = (typeof CONVERSATION_STATUSES)[number]

export interface Conversation {
  id: number
  contact_id: number | null
  account_id: number
  account_label: string
  peer_id: number | null
  peer_username: string | null
  label: string
  last_message_at: string | null
  last_message_preview: string | null
  unread_count: number
  status: string
  archived: boolean
}

export interface SavedContact {
  id: number
  label: string
  username: string | null
  phone: string | null
  telegram_user_id: number | null
  stage: string
  source: string | null
  consent: boolean
}

export interface InboxMessage {
  id: number
  conversation_id: number
  direction: 'in' | 'out'
  account_id: number | null
  sender: string
  type: string
  body: string | null
  media_ref: string | null
  status: string
  created_at: string | null
}

export interface Thread {
  conversation: Conversation
  messages: InboxMessage[]
  contact: Record<string, unknown> | null
}

export interface InboxEvent {
  type:
    | 'message'
    | 'conversation'
    | 'connected'
    | 'bot_message'
    | 'bot_conversation'
    | 'dashboard'
  conversation?: Conversation | Record<string, unknown>
  message?: InboxMessage | Record<string, unknown>
  snapshot?: DashboardSnapshot
}

async function fetchBlob(path: string): Promise<Blob> {
  const { accessToken } = useAuth.getState()
  const res = await fetch(`/api${path}`, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  })
  if (!res.ok) throw new ApiError(res.status, res.statusText)
  return res.blob()
}

async function multipartForm<T>(path: string, form: FormData): Promise<T> {
  const { accessToken } = useAuth.getState()
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

export const inboxApi = {
  listConversations: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString()
    return apiFetch<Conversation[]>(`/inbox/conversations${qs ? `?${qs}` : ''}`)
  },
  getThread: (id: number) => apiFetch<Thread>(`/inbox/conversations/${id}`),
  // Save an unlinked inbox peer as a CRM contact.
  saveContact: (id: number) =>
    apiFetch<SavedContact>(`/inbox/conversations/${id}/save-contact`, { method: 'POST' }),
  // Archive / unarchive (history kept); delete removes our copy only.
  archive: (id: number, archived: boolean) =>
    apiFetch<Conversation>(`/inbox/conversations/${id}/archive`, {
      method: 'POST',
      body: JSON.stringify({ archived }),
    }),
  remove: (id: number) => apiFetch<void>(`/inbox/conversations/${id}`, { method: 'DELETE' }),
  // Media is streamed from Telegram on demand (never stored on the VPS). Fetched
  // as an authed blob so the token stays in the header, not the URL.
  media: (messageId: number) => fetchBlob(`/inbox/messages/${messageId}/media`),
  // Send media/voice from the composer — uploaded straight to Telegram (not stored).
  sendMedia: (id: number, file: File, kind: string, caption?: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('kind', kind)
    if (caption) form.append('caption', caption)
    return multipartForm<InboxMessage>(`/inbox/conversations/${id}/send-media`, form)
  },
  markRead: (id: number) =>
    apiFetch<Conversation>(`/inbox/conversations/${id}/read`, { method: 'POST' }),
  setStatus: (id: number, status: ConversationStatus) =>
    apiFetch<Conversation>(`/inbox/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  sendReply: (id: number, body: { type: string; body?: string; media_url?: string }) =>
    apiFetch<InboxMessage>(`/inbox/conversations/${id}/send`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  simulateIncoming: (data: {
    account_id: number
    peer_id?: number
    peer_name?: string
    peer_username?: string
    text?: string
    msg_type?: string
    media_ref?: string
    tg_message_id?: number
  }) =>
    apiFetch<Conversation>('/inbox/simulate-incoming', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
}

// ---- Bots (Phase 10) ----

export interface Bot {
  id: number
  name: string | null
  username: string | null
  mode: string
  status: string
  created_at: string
}

export interface BotDetail extends Bot {
  counts: Record<string, number>
  deep_link: string
}

export interface BotSubscriber {
  id: number
  telegram_user_id: number
  name: string | null
  utm_source: string | null
  is_active: boolean
  is_subscribed: boolean
}

export interface BotConversation {
  id: number
  bot_id: number
  subscriber_id: number
  label: string
  last_message_at: string | null
  last_message_preview: string | null
  unread_count: number
  status: string
}

export interface BotMessage {
  id: number
  bot_conversation_id: number
  direction: 'in' | 'out'
  sender: string
  type: string
  body: string | null
  created_at: string | null
}

export interface BotThread {
  conversation: BotConversation
  messages: BotMessage[]
}

export const botsApi = {
  list: () => apiFetch<Bot[]>('/bots'),
  add: (token: string) =>
    apiFetch<Bot>('/bots', { method: 'POST', body: JSON.stringify({ token }) }),
  get: (id: number) => apiFetch<BotDetail>(`/bots/${id}`),
  remove: (id: number) => apiFetch<void>(`/bots/${id}`, { method: 'DELETE' }),
  start: (id: number) => apiFetch<Bot>(`/bots/${id}/start`, { method: 'POST' }),
  stop: (id: number) => apiFetch<Bot>(`/bots/${id}/stop`, { method: 'POST' }),
  subscribers: (id: number) => apiFetch<BotSubscriber[]>(`/bots/${id}/subscribers`),
  conversations: (id: number) => apiFetch<BotConversation[]>(`/bots/${id}/conversations`),
  thread: (id: number, cid: number) =>
    apiFetch<BotThread>(`/bots/${id}/conversations/${cid}`),
  markRead: (id: number, cid: number) =>
    apiFetch<BotConversation>(`/bots/${id}/conversations/${cid}/read`, { method: 'POST' }),
  reply: (id: number, cid: number, text: string) =>
    apiFetch<BotMessage>(`/bots/${id}/conversations/${cid}/reply`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  post: (id: number, body: { chat_id: string; text: string; image_url?: string | null }) =>
    apiFetch<{ sent: boolean }>(`/bots/${id}/post`, { method: 'POST', body: JSON.stringify(body) }),
  broadcast: (id: number, text: string) =>
    apiFetch<{ sent: number; recipients: number }>(`/bots/${id}/broadcast`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  simulateIncoming: (id: number, body: { telegram_user_id: number; name?: string; text: string; utm_source?: string }) =>
    apiFetch<BotConversation>(`/bots/${id}/simulate-incoming`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

// ---- Campaigns + templates (Phase 9) ----

export interface Template {
  id: number
  name: string
  body: string
  include_link: boolean
  link_url: string | null
  variant_group: string
  variant_label: string
  created_at: string
}

export interface Campaign {
  id: number
  name: string
  action: string
  destination_id: number | null
  segment: Record<string, unknown>
  steps: Array<Record<string, unknown>>
  ab_test: boolean
  status: string
  created_at: string
  started_at: string | null
}

export interface CampaignTarget {
  id: number
  contact_id: number
  contact_label: string
  step: number
  template_id: number | null
  account_id: number | null
  result: string
  error: string | null
}

export interface ABRow {
  template_id: number | null
  label: string
  name: string
  queued: number
  sent: number
  joined: number
  failed: number
  skipped: number
  replied: number
}

export interface CampaignDetail extends Campaign {
  stats: Record<string, number>
  ab_report: ABRow[]
  targets: CampaignTarget[]
}

export interface CampaignTickResult {
  sent: number
  joined: number
  failed: number
  skipped: number
  paused: boolean
  actions: Array<Record<string, unknown>>
  warning: string | null
}

export interface CreateTemplateInput {
  name: string
  body: string
  include_link?: boolean
  link_url?: string | null
  variant_group: string
  variant_label?: string
}

export interface CampaignStep {
  offset_hours: number
  variant_group?: string | null
}

export interface CreateCampaignInput {
  name: string
  action: string
  destination_id?: number | null
  segment: Record<string, unknown>
  steps: CampaignStep[]
  ab_test: boolean
}

export const templatesApi = {
  list: () => apiFetch<Template[]>('/templates'),
  create: (data: CreateTemplateInput) =>
    apiFetch<Template>('/templates', { method: 'POST', body: JSON.stringify(data) }),
}

export const campaignsApi = {
  list: () => apiFetch<Campaign[]>('/campaigns'),
  create: (data: CreateCampaignInput) =>
    apiFetch<Campaign>('/campaigns', { method: 'POST', body: JSON.stringify(data) }),
  get: (id: number) => apiFetch<CampaignDetail>(`/campaigns/${id}`),
  start: (id: number) =>
    apiFetch<CampaignDetail>(`/campaigns/${id}/start`, { method: 'POST' }),
  pause: (id: number) =>
    apiFetch<CampaignDetail>(`/campaigns/${id}/pause`, { method: 'POST' }),
  stop: (id: number) =>
    apiFetch<CampaignDetail>(`/campaigns/${id}/stop`, { method: 'POST' }),
  tick: (id: number) =>
    apiFetch<CampaignTickResult>(`/campaigns/${id}/tick`, { method: 'POST' }),
}

// ---- Destinations / Add members (Phase 8) ----

export interface Destination {
  id: number
  title: string | null
  link: string
  tg_entity_id: number | null
  type: string
  invite_link: string | null
  created_at: string
}

export interface Membership {
  id: number
  contact_id: number
  contact_label: string
  state: string
  method: string | null
  account_id: number | null
  error: string | null
}

export interface DestinationDetail extends Destination {
  stats: Record<string, number>
  memberships: Membership[]
}

export interface AddMembersResult {
  queued: number
  skipped_existing: number
}

export interface AddTickResult {
  added: number
  invited: number
  failed: number
  paused: boolean
  actions: Array<Record<string, unknown>>
  warning: string | null
}

export const destinationsApi = {
  list: () => apiFetch<Destination[]>('/destinations'),
  register: (link: string) =>
    apiFetch<Destination>('/destinations', { method: 'POST', body: JSON.stringify({ link }) }),
  get: (id: number) => apiFetch<DestinationDetail>(`/destinations/${id}`),
  remove: (id: number) => apiFetch<void>(`/destinations/${id}`, { method: 'DELETE' }),
  addMembers: (id: number, body: { contact_ids?: number[]; identifiers?: string[] }) =>
    apiFetch<AddMembersResult>(`/destinations/${id}/add-members`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  tick: (id: number) =>
    apiFetch<AddTickResult>(`/destinations/${id}/add-members/tick`, { method: 'POST' }),
}

// ---- Sender (Phase 7) ----

export interface SendJob {
  id: number
  name: string
  template: string
  include_link: boolean
  link_url: string | null
  suppress_link_first: boolean
  active_start: string
  active_end: string
  status: string
  created_at: string
  started_at: string | null
}

export interface SendTarget {
  id: number
  contact_id: number
  contact_label: string
  account_id: number | null
  status: string
  error: string | null
  rendered_body: string | null
}

export interface SendJobDetail extends SendJob {
  stats: Record<string, number>
  targets: SendTarget[]
}

export interface SendTickResult {
  sent: number
  skipped: number
  failed: number
  paused: boolean
  actions: Array<Record<string, unknown>>
  warning: string | null
}

export interface CreateSendJobInput {
  name: string
  template: string
  include_link: boolean
  link_url?: string | null
  suppress_link_first: boolean
}

export const senderApi = {
  listJobs: () => apiFetch<SendJob[]>('/sender/jobs'),
  createJob: (data: CreateSendJobInput) =>
    apiFetch<SendJob>('/sender/jobs', { method: 'POST', body: JSON.stringify(data) }),
  getJob: (id: number) => apiFetch<SendJobDetail>(`/sender/jobs/${id}`),
  addTargets: (id: number, body: { contact_ids?: number[]; source?: string }) =>
    apiFetch<SendJobDetail>(`/sender/jobs/${id}/targets`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  start: (id: number) =>
    apiFetch<SendJobDetail>(`/sender/jobs/${id}/start`, { method: 'POST' }),
  pause: (id: number) =>
    apiFetch<SendJobDetail>(`/sender/jobs/${id}/pause`, { method: 'POST' }),
  stop: (id: number) =>
    apiFetch<SendJobDetail>(`/sender/jobs/${id}/stop`, { method: 'POST' }),
  tick: (id: number) =>
    apiFetch<SendTickResult>(`/sender/jobs/${id}/tick`, { method: 'POST' }),
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

// ---- Dashboard, analytics + referral (Phase 11) ----

export interface RunningCampaign {
  id: number
  name: string
  action: string
  total: number
  done: number
  sent: number
  joined: number
  failed: number
}

export interface DashboardEvent {
  id: number
  type: string
  entity_ref: string | null
  meta: Record<string, unknown>
  created_at: string | null
}

export interface DashboardSnapshot {
  generated_at: string
  accounts: Record<string, number>
  caps: { actions_today: number; daily_cap: number; pct: number }
  queue: { send_targets: number; campaign_targets: number; total: number }
  proxies: Record<string, number>
  throughput: { sends_today: number; sends_last_hour: number }
  running_campaigns: RunningCampaign[]
  recent_events: DashboardEvent[]
}

export interface FunnelData {
  total: number
  stages: Record<string, number>
  reached: Record<string, number>
  conversion_pct: number
}

export interface SourceRow {
  source: string
  total: number
  conversion_pct: number
  [key: string]: number | string
}

export interface AccountHealthRow {
  id: number
  label: string
  status: string
  spam_state: string
  warmup_stage: number
  actions_today: number
  daily_cap: number
  logged_in: boolean
  last_action_at: string | null
}

export interface CampaignSummaryRow {
  id: number
  name: string
  action: string
  status: string
  ab_test: boolean
  targets: number
  sent: number
  joined: number
  replied: number
  failed: number
  queued: number
}

export interface UtmRow {
  utm_source: string
  subscribers: number
  subscribed: number
  converted: number
}

export interface ReferralRow {
  referral_id: number
  subscriber_id: number
  label: string
  bot_name: string | null
  invite_code: string
  invited_count: number
  rewarded: boolean
}

export interface AnalyticsOverview {
  funnel: FunnelData
  per_source: SourceRow[]
  per_account: AccountHealthRow[]
  campaigns: CampaignSummaryRow[]
  utm: UtmRow[]
  referrals: ReferralRow[]
}

export interface ReferralDetail {
  id: number
  referrer_subscriber_id: number
  invite_code: string
  invited_count: number
  rewarded: boolean
  created_at: string
  deep_link: string
}

// ---- Backup & Restore center (Phase 15.2) ----

export const BACKUP_SCOPES = ['database', 'sessions', 'settings'] as const
export type BackupScope = (typeof BACKUP_SCOPES)[number]

export interface BackupItem {
  name: string
  size: number
  created_at: string
  scope: string[]
  app_version: string | null
  db_file: string | null
}

export interface BackupSettings {
  enabled: boolean
  interval_days: number
  scope: string[]
}

export const backupsApi = {
  list: () => apiFetch<BackupItem[]>('/backups'),
  create: (scope: string[]) =>
    apiFetch<BackupItem>('/backups', { method: 'POST', body: JSON.stringify({ scope }) }),
  remove: (name: string) =>
    apiFetch<void>(`/backups/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  restore: (name: string) =>
    apiFetch<{ name: string; restored: string[] }>(
      `/backups/${encodeURIComponent(name)}/restore`,
      { method: 'POST' },
    ),
  getSettings: () => apiFetch<BackupSettings>('/backups/settings'),
  saveSettings: (s: Partial<BackupSettings>) =>
    apiFetch<BackupSettings>('/backups/settings', { method: 'PUT', body: JSON.stringify(s) }),
  // Archives hold sessions + full data — fetched as an authed blob, never a raw URL.
  download: async (name: string) => {
    const blob = await fetchBlob(`/backups/${encodeURIComponent(name)}/download`)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
  },
}

export const analyticsApi = {
  dashboard: () => apiFetch<DashboardSnapshot>('/analytics/dashboard'),
  broadcastDashboard: () =>
    apiFetch<DashboardSnapshot>('/analytics/dashboard/broadcast', { method: 'POST' }),
  overview: () => apiFetch<AnalyticsOverview>('/analytics'),
  referrals: () => apiFetch<ReferralRow[]>('/analytics/referrals'),
  createReferral: (subscriber_id: number) =>
    apiFetch<ReferralDetail>('/analytics/referrals', {
      method: 'POST',
      body: JSON.stringify({ subscriber_id }),
    }),
  recordReferral: (invite_code: string) =>
    apiFetch<{ id: number; invite_code: string; invited_count: number; rewarded: boolean }>(
      '/analytics/referrals/record',
      { method: 'POST', body: JSON.stringify({ invite_code }) },
    ),
  reward: (id: number, rewarded = true) =>
    apiFetch<{ id: number; invited_count: number; rewarded: boolean }>(
      `/analytics/referrals/${id}/reward`,
      { method: 'POST', body: JSON.stringify({ rewarded }) },
    ),
}
