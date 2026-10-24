import type { ApiErrorBody } from './types'

/** A failed API call. `status` 0 means the request never reached the server (offline, aborted by the browser, DNS ...). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly location: string | null = null,
    readonly fields: Record<string, string> | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  get notFound(): boolean { return this.status === 404 }
  /** The content exists under a new address (a renamed slug): `location` says where. */
  get moved(): boolean { return this.status === 404 && this.code === 'moved' && !!this.location }
}

export type Query = Record<string, string | number | boolean | null | undefined>

export function withQuery(path: string, query?: Query): string {
  if (!query) return path
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === null || v === undefined || v === '' || v === false) continue
    qs.set(k, String(v))
  }
  const text = qs.toString()
  return text ? `${path}?${text}` : path
}

/** GET a public JSON endpoint. The browser's HTTP cache handles ETag / 304 (the server answers `Cache-Control: no-cache` + weak ETag). */
export async function getJSON<T>(path: string, opts: { query?: Query; signal?: AbortSignal } = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(withQuery(path, opts.query), { headers: { Accept: 'application/json' }, signal: opts.signal ?? null })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(0, 'network', '网络好像断了，请检查连接后再试。')
  }
  if (res.ok) {
    try {
      return (await res.json()) as T
    } catch {
      throw new ApiError(res.status, 'bad_response', '服务器返回的内容看不懂。')
    }
  }
  let body: Partial<ApiErrorBody> = {}
  try { body = (await res.json()) as ApiErrorBody } catch { /* an HTML error page from a proxy, for instance */ }
  const e = body.error
  throw new ApiError(res.status, e?.code ?? `http_${res.status}`, e?.message ?? '出错了。', e?.location ?? null, e?.fields ?? null)
}

export const isAbort = (err: unknown): boolean => err instanceof DOMException && err.name === 'AbortError'

/** The anonymous visit beacon: fire and forget. */
export function beacon(path: string, referrer: string): void {
  try {
    const body = JSON.stringify({ p: path.slice(0, 300), r: referrer.slice(0, 300) })
    if (navigator.sendBeacon?.('/api/track', new Blob([body], { type: 'application/json' }))) return
    void fetch('/api/track', { method: 'POST', body, headers: { 'Content-Type': 'application/json' }, keepalive: true }).catch(() => undefined)
  } catch { /* statistics are optional */ }
}
