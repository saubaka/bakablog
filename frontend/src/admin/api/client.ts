/* The admin's way to talk to /api/admin: JSON in and out, the CSRF token on every write, one error type.
   A 401 means the session is gone (expired, signed out elsewhere): the shell sends the person to the login page and brings them back. */
import { shallowRef } from 'vue'

export class AdminError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly fields: Record<string, string> = {},
    readonly extra: Record<string, unknown> = {},
  ) {
    super(message)
    this.name = 'AdminError'
  }

  get conflict(): boolean { return this.status === 409 }
  get retryAfter(): number { return Number(this.extra.retry_after ?? 0) }
  /** The first field message, for a toast when the form has no place to show it. */
  get firstField(): string { return Object.values(this.fields)[0] ?? '' }
}

export type Query = Record<string, string | number | boolean | null | undefined>

export const csrf = shallowRef('')
let onUnauthorized: () => void = () => undefined
let refreshCsrf: (() => Promise<void>) | null = null
export function configureClient(opts: { onUnauthorized: () => void; refreshCsrf: () => Promise<void> }): void {
  onUnauthorized = opts.onUnauthorized
  refreshCsrf = opts.refreshCsrf
}

export function withQuery(path: string, query?: Query): string {
  if (!query) return path
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === null || v === undefined || v === '' || v === false) continue
    qs.set(k, v === true ? '1' : String(v))
  }
  const text = qs.toString()
  return text ? `${path}?${text}` : path
}

interface Options { query?: Query; body?: unknown; form?: FormData; signal?: AbortSignal; quiet401?: boolean }

async function send(method: string, path: string, opts: Options, retried = false): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.body) }
  if (method !== 'GET' && method !== 'HEAD') headers['X-CSRF-Token'] = csrf.value
  let res: Response
  try {
    res = await fetch(withQuery(`/api/admin${path}`, opts.query), { method, headers, body, signal: opts.signal ?? null, credentials: 'same-origin' })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new AdminError(0, 'network', '连不上服务器，请检查网络后再试。')
  }
  if (res.status === 403 && !retried && refreshCsrf) {
    // the page is older than the session's token (another tab signed in again): fetch a fresh token once and repeat
    const peek = await res.clone().json().catch(() => null) as { error?: { code?: string } } | null
    if (peek?.error?.code === 'csrf') { await refreshCsrf().catch(() => undefined); return send(method, path, opts, true) }
  }
  return res
}

async function fail(res: Response, quiet401: boolean): Promise<never> {
  let body: { error?: Record<string, unknown> } = {}
  try { body = (await res.json()) as typeof body } catch { /* a proxy's HTML page */ }
  const e = body.error ?? {}
  const { code, message, fields, ...extra } = e as { code?: string; message?: string; fields?: Record<string, string> }
  if (res.status === 401 && !quiet401) onUnauthorized()
  throw new AdminError(res.status, code ?? `http_${res.status}`, message ?? '出错了。', fields ?? {}, extra)
}

async function call<T>(method: string, path: string, opts: Options = {}): Promise<T> {
  const res = await send(method, path, opts)
  if (!res.ok) return fail(res, !!opts.quiet401)
  if (res.status === 204) return undefined as T
  const type = res.headers.get('Content-Type') ?? ''
  return (type.includes('json') ? await res.json() : await res.blob()) as T
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => call<T>('GET', path, { ...(query ? { query } : {}), ...(signal ? { signal } : {}) }),
  post: <T>(path: string, body?: unknown, opts: Options = {}) => call<T>('POST', path, { ...opts, ...(body !== undefined ? { body } : {}) }),
  put: <T>(path: string, body?: unknown) => call<T>('PUT', path, { body }),
  patch: <T>(path: string, body?: unknown) => call<T>('PATCH', path, { body }),
  del: <T>(path: string, query?: Query) => call<T>('DELETE', path, query ? { query } : {}),
  upload: <T>(path: string, form: FormData) => call<T>('POST', path, { form }),
  /** The raw response, for downloads that should be saved rather than parsed. */
  raw: async (method: string, path: string, query?: Query): Promise<Response> => {
    const res = await send(method, path, query ? { query } : {})
    if (!res.ok) return fail(res, false)
    return res
  },
}

/** Send a file to the browser's download flow (backups, exports). */
export async function download(path: string, filename: string, query?: Query): Promise<void> {
  const res = await api.raw('GET', path, query)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
