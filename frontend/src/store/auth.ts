import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { applyTheme, type Theme } from '../lib/theme'

export type Role = 'admin' | 'manager' | 'agent'

export interface User {
  id: number
  email: string
  full_name: string | null
  role: Role
  theme: Theme
  is_active: boolean
  created_at: string
  last_login: string | null
}

interface TokenPair {
  access_token: string
  refresh_token: string
}

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  status: 'idle' | 'loading'
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<boolean>
  setUser: (user: User) => void
}

async function readDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    /* ignore non-JSON bodies */
  }
  return fallback
}

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      status: 'idle',

      login: async (email, password) => {
        set({ status: 'loading' })
        try {
          const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
          })
          if (!res.ok) {
            throw new Error(await readDetail(res, 'Login failed'))
          }
          const tokens = (await res.json()) as TokenPair
          const meRes = await fetch('/api/auth/me', {
            headers: { Authorization: `Bearer ${tokens.access_token}` },
          })
          if (!meRes.ok) throw new Error('Could not load your profile')
          const user = (await meRes.json()) as User
          set({
            user,
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
            status: 'idle',
          })
          applyTheme(user.theme)
        } catch (err) {
          set({ status: 'idle' })
          throw err
        }
      },

      logout: () => set({ user: null, accessToken: null, refreshToken: null }),

      refresh: async () => {
        const { refreshToken } = get()
        if (!refreshToken) return false
        const res = await fetch('/api/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        })
        if (!res.ok) return false
        const data = (await res.json()) as { access_token: string }
        set({ accessToken: data.access_token })
        return true
      },

      setUser: (user) => {
        set({ user })
        applyTheme(user.theme)
      },
    }),
    {
      name: 'tgcrm-auth',
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
    },
  ),
)
