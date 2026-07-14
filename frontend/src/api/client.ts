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
