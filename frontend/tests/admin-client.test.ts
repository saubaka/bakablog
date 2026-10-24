import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminError, api, configureClient, csrf, withQuery } from '@/admin/api/client'

const json = (status: number, body: unknown, headers: Record<string, string> = {}): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })

describe('withQuery', () => {
  it('drops empty values and writes booleans as 1', () => {
    expect(withQuery('/posts', { q: '', page: 2, trashed: true, off: false, none: null, gone: undefined, tag: 'a b' })).toBe('/posts?page=2&trashed=1&tag=a+b')
    expect(withQuery('/posts')).toBe('/posts')
    expect(withQuery('/posts', { q: '' })).toBe('/posts')
  })
})

describe('AdminError', () => {
  it('carries the status, the code, field messages and extras', () => {
    const e = new AdminError(429, 'locked', '稍后再试', { username: '不对' }, { retry_after: 30 })
    expect(e.conflict).toBe(false)
    expect(e.retryAfter).toBe(30)
    expect(e.firstField).toBe('不对')
    expect(new AdminError(409, 'conflict', 'x').conflict).toBe(true)
    expect(new AdminError(500, 'x', 'y').retryAfter).toBe(0)
  })
})

describe('the admin API client', () => {
  let calls: { url: string; init: RequestInit }[]
  let queue: (Response | Error)[]
  let unauthorized: ReturnType<typeof vi.fn>
  let refresh: ReturnType<typeof vi.fn>

  beforeEach(() => {
    calls = []
    queue = []
    unauthorized = vi.fn()
    refresh = vi.fn(async () => { csrf.value = 'fresh-token' })
    csrf.value = 'old-token'
    configureClient({ onUnauthorized: unauthorized, refreshCsrf: refresh })
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init })
      const next = queue.shift()
      if (next instanceof Error) throw next
      return next ?? json(200, {})
    }))
  })
  afterEach(() => { vi.unstubAllGlobals() })

  const header = (i: number, name: string): string | undefined => (calls[i]?.init.headers as Record<string, string>)[name]

  it('reads: GET /api/admin/... with the query, no token, JSON accepted', async () => {
    queue.push(json(200, { items: [] }))
    await api.get('/posts', { page: 2, q: '' })
    expect(calls[0]?.url).toBe('/api/admin/posts?page=2')
    expect(calls[0]?.init.method).toBe('GET')
    expect(header(0, 'X-CSRF-Token')).toBeUndefined()
  })

  it('writes carry the CSRF token and a JSON body; uploads are not JSON-encoded', async () => {
    queue.push(json(200, {}), json(200, {}))
    await api.post('/posts', { title: 'x' })
    expect(header(0, 'X-CSRF-Token')).toBe('old-token')
    expect(header(0, 'Content-Type')).toBe('application/json')
    expect(calls[0]?.init.body).toBe('{"title":"x"}')
    const form = new FormData()
    form.append('file', new Blob(['x']), 'a.png')
    await api.upload('/media', form)
    expect(calls[1]?.init.body).toBe(form)
    expect(header(1, 'Content-Type')).toBeUndefined()    // the browser writes the multipart boundary itself
    expect(header(1, 'X-CSRF-Token')).toBe('old-token')
  })

  it('an error answer becomes an AdminError with the code, the message and the field messages', async () => {
    queue.push(json(422, { error: { code: 'invalid', message: '有问题', fields: { title: '太长' }, limit: 3 } }))
    const e = await api.post('/posts', {}).catch((x: unknown) => x)
    expect(e).toBeInstanceOf(AdminError)
    expect(e).toMatchObject({ status: 422, code: 'invalid', message: '有问题', fields: { title: '太长' }, extra: { limit: 3 } })
  })

  it('a proxy error page (not JSON) still gives a readable error', async () => {
    queue.push(new Response('<html>bad gateway</html>', { status: 502 }))
    const e = await api.get('/x').catch((x: unknown) => x)
    expect(e).toMatchObject({ status: 502, code: 'http_502' })
  })

  it('401 tells the shell to send the person to the login page; the login call itself is quiet', async () => {
    queue.push(json(401, { error: { code: 'unauthorized', message: '请先登录' } }), json(401, { error: { code: 'bad_credentials', message: '不对' } }))
    await api.get('/posts').catch(() => undefined)
    expect(unauthorized).toHaveBeenCalledTimes(1)
    await api.post('/auth/login', {}, { quiet401: true }).catch(() => undefined)
    expect(unauthorized).toHaveBeenCalledTimes(1)
  })

  it('a stale CSRF token is replaced once and the write repeated', async () => {
    queue.push(json(403, { error: { code: 'csrf', message: '令牌过期' } }), json(200, { ok: true }))
    const out = await api.post<{ ok: boolean }>('/posts', { title: 'x' })
    expect(out.ok).toBe(true)
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(calls).toHaveLength(2)
    expect(header(1, 'X-CSRF-Token')).toBe('fresh-token')
  })

  it('a second CSRF failure is reported, not retried forever', async () => {
    queue.push(json(403, { error: { code: 'csrf', message: 'a' } }), json(403, { error: { code: 'csrf', message: 'b' } }))
    await expect(api.post('/posts', {})).rejects.toMatchObject({ status: 403, code: 'csrf' })
    expect(calls).toHaveLength(2)
  })

  it('a network failure is an AdminError with status 0 and plain words', async () => {
    queue.push(new TypeError('Failed to fetch'))
    await expect(api.get('/posts')).rejects.toMatchObject({ status: 0, code: 'network' })
  })

  it('a cancelled request stays an AbortError (the page that cancelled it knows)', async () => {
    queue.push(new DOMException('aborted', 'AbortError'))
    await expect(api.get('/posts')).rejects.toMatchObject({ name: 'AbortError' })
  })
})
