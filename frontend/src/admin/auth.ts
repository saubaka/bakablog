import { reactive } from 'vue'
import { api, csrf } from './api/client'
import type { AdminSession, AdminUser, AuthStatus, MeResponse } from './types'

/** Who is signed in. `ready` turns true once the first status check has answered, so the shell never flashes the login page at a signed-in person. */
export const auth = reactive({
  ready: false,
  setupRequired: false,
  user: null as AdminUser | null,
  session: null as AdminSession | null,
})

function apply(me: MeResponse): void {
  auth.user = me.user
  auth.session = me.session
  csrf.value = me.csrf_token
}

export function clear(): void {
  auth.user = null
  auth.session = null
  csrf.value = ''
}

export async function loadMe(): Promise<void> {
  apply(await api.get<MeResponse>('/auth/me'))
}

export async function bootstrap(): Promise<void> {
  try {
    const st = await api.get<AuthStatus>('/auth/status')
    auth.setupRequired = st.setup_required
    if (st.authenticated) await loadMe().catch(clear)
  } finally {
    auth.ready = true
  }
}

export async function login(username: string, password: string, code?: string): Promise<void> {
  apply(await api.post<MeResponse>('/auth/login', { username, password, ...(code ? { code } : {}) }, { quiet401: true }))
  auth.setupRequired = false
}

export async function setup(token: string, username: string, password: string, email?: string): Promise<void> {
  apply(await api.post<MeResponse>('/auth/setup', { token, username, password, ...(email ? { email } : {}) }, { quiet401: true }))
  auth.setupRequired = false
}

export async function logout(): Promise<void> {
  try { await api.post('/auth/logout', undefined, { quiet401: true }) } finally { clear() }
}
