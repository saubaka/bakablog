import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getJSON, withQuery } from '@/shared/api'
import { blogQuery, loadRoute, momentsQuery, postsParams, PER_PAGE } from '@/public/data'
import { headFor } from '@/public/head'
import type { PageState } from '@/public/state'
import type { BootData, PostsPage, SiteInfo } from '@/shared/types'
import home from '@samples/home.json'
import moments from '@samples/moments.json'
import post from '@samples/post.json'
import posts from '@samples/posts.json'
import site from '@samples/site.json'
import taxonomy from '@samples/taxonomy.json'
import type { RouteLocationNormalized } from 'vue-router'

const S = site as unknown as SiteInfo
const route = (name: string, path: string, params: Record<string, string> = {}, query: Record<string, string> = {}) =>
  ({ name, path, params, query, fullPath: path, hash: '', matched: [], meta: {}, redirectedFrom: undefined }) as unknown as RouteLocationNormalized

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('query strings', () => {
  it('blog query is lenient: junk becomes the default', () => {
    expect(blogQuery({ page: 'abc', sort: 'nonsense', q: '  hi  ' })).toEqual({ page: 1, sort: 'new', q: 'hi' })
    expect(blogQuery({ page: '3', sort: 'old' })).toEqual({ page: 3, sort: 'old', q: '' })
    expect(blogQuery({ page: '-4' }).page).toBe(1)
    expect(blogQuery({ q: 'x'.repeat(300) }).q.length).toBe(100)
    expect(blogQuery({ page: ['2', '5'] }).page).toBe(2)
  })
  it('moments query accepts only well-formed months', () => {
    expect(momentsQuery({ month: '2026-10', tag: 'css' })).toEqual({ month: '2026-10', tag: 'css', mood: '' })
    expect(momentsQuery({ month: '2026-13' }).month).toBe('')
    expect(momentsQuery({ month: 'oct' }).month).toBe('')
  })
  it('list requests carry the page size and drop defaults', () => {
    expect(withQuery('/api/posts', postsParams({ page: 1, q: '', sort: 'new' }))).toBe(`/api/posts?per=${PER_PAGE}`)
    expect(withQuery('/api/posts', postsParams({ page: 2, q: 'a b', sort: 'old' }, { tag: 'x' }))).toBe(`/api/posts?page=2&per=${PER_PAGE}&q=a+b&sort=old&tag=x`)
  })
})

describe('getJSON', () => {
  const fetchMock = (res: { ok?: boolean; status?: number; payload?: unknown; fail?: boolean }) =>
    vi.stubGlobal('fetch', vi.fn(async () => { if (res.fail) throw new TypeError('offline'); return { ok: res.ok ?? true, status: res.status ?? 200, json: async () => res.payload } as Response }))

  it('returns the body of a good answer', async () => {
    fetchMock({ payload: { a: 1 } })
    expect(await getJSON('/api/x')).toEqual({ a: 1 })
  })
  it('turns the server error format into ApiError, with the new address of a moved page', async () => {
    fetchMock({ ok: false, status: 404, payload: { error: { code: 'moved', message: '换了地址', location: '/blog/new' } } })
    const err = await getJSON('/api/posts/old').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).moved).toBe(true)
    expect((err as ApiError).location).toBe('/blog/new')
  })
  it('a failed request is status 0, and a non-JSON error page is still an ApiError', async () => {
    fetchMock({ fail: true })
    expect(await getJSON('/api/x').catch((e: ApiError) => e.status)).toBe(0)
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 502, json: async () => { throw new Error('html') } }) as unknown as Response))
    const e = (await getJSON('/api/x').catch((x: unknown) => x)) as ApiError
    expect(e.status).toBe(502)
    expect(e.code).toBe('http_502')
  })
})

describe('loadRoute', () => {
  const signal = new AbortController().signal
  const boot = (kind: BootData['kind'], path: string, data: unknown, extra: object = {}): BootData => ({ path, kind, status: 200, site: S, data, ...extra }) as BootData

  it('uses the server\'s first-screen data without a request', async () => {
    const f = vi.fn(); vi.stubGlobal('fetch', f)
    const r = await loadRoute(route('home', '/'), signal, boot('home', '/', home)) as PageState
    expect(r.kind).toBe('home')
    const b = await loadRoute(route('blog', '/blog'), signal, boot('blog', '/blog', posts, { taxonomy })) as Extract<PageState, { kind: 'blog' }>
    expect(b.taxonomy?.total_posts).toBe((taxonomy as { total_posts: number }).total_posts)
    expect(f).not.toHaveBeenCalled()
  })

  it('ignores first-screen data that belongs to another address', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => home }) as Response))
    const r = await loadRoute(route('home', '/'), signal, boot('blog', '/blog', posts)) as PageState
    expect(r.kind).toBe('home')
    expect(fetch).toHaveBeenCalledWith('/api/home', expect.anything())
  })

  it('the server\'s own 404 page is used as is', async () => {
    const r = await loadRoute(route('post', '/blog/nope', { slug: 'nope' }), signal, { ...boot('404', '/blog/nope', { not_found: true, recent: [] }), status: 404 }) as PageState
    expect(r.kind).toBe('404')
  })

  it('fetches by route and decodes the slug', async () => {
    const urls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (u: string) => { urls.push(u); return { ok: true, status: 200, json: async () => (u.startsWith('/api/posts/') ? post : u.startsWith('/api/taxonomy') ? taxonomy : u.startsWith('/api/moments') ? moments : posts) } as Response }))
    await loadRoute(route('post', '/blog/a b', { slug: 'a b' }, { preview: 'tok' }), signal, null)
    await loadRoute(route('category', '/category/dai-ma', { slug: 'dai-ma' }, { page: '2' }), signal, null)
    await loadRoute(route('moments', '/moments', {}, { tag: 'css' }), signal, null)
    expect(urls[0]).toBe('/api/posts/a%20b?preview=tok')
    expect(urls.some((u) => u === `/api/posts?page=2&per=${PER_PAGE}&category=dai-ma`)).toBe(true)
    expect(urls.some((u) => u.startsWith('/api/moments?') && u.includes('tag=css') && u.includes('limit=10'))).toBe(true)
  })

  it('a renamed address becomes a redirect; a missing one becomes the 404 page; other errors propagate', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, json: async () => ({ error: { code: 'moved', message: 'm', location: '/blog/new' } }) }) as Response))
    expect(await loadRoute(route('post', '/blog/old', { slug: 'old' }), signal, null)).toEqual({ redirect: '/blog/new' })
    vi.stubGlobal('fetch', vi.fn(async (u: string) => (u.includes('/api/posts/') ? ({ ok: false, status: 404, json: async () => ({ error: { code: 'not_found', message: 'x' } }) } as Response) : ({ ok: true, status: 200, json: async () => posts } as Response))))
    const nf = await loadRoute(route('post', '/blog/zzz', { slug: 'zzz' }), signal, null) as PageState
    expect(nf.kind).toBe('404')
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500, json: async () => ({ error: { code: 'server', message: 'boom' } }) }) as Response))
    await expect(loadRoute(route('archive', '/archive'), signal, null)).rejects.toBeInstanceOf(ApiError)
  })
})

describe('head of a page', () => {
  const list = posts as unknown as PostsPage
  it('home, blog, post, search, 404', () => {
    expect(headFor({ kind: 'home', status: 200, data: home as never }, S, '/').title).toBe(`${S.name} · ${S.tagline}`)
    const blog = headFor({ kind: 'blog', status: 200, data: { ...list, page: 2 }, taxonomy: null, query: { page: 2, q: '', sort: 'new' } }, S, '/blog?page=2')
    expect(blog.title).toBe(`博客 · 第 2 页 · ${S.name}`)
    expect(blog.canonical).toBe(`${S.origin}/blog?page=2`)
    expect(blog.noindex).toBe(false)
    const filtered = headFor({ kind: 'blog', status: 200, data: list, taxonomy: null, query: { page: 1, q: 'x', sort: 'new' } }, S, '/blog?q=x')
    expect(filtered.noindex).toBe(true)
    expect(filtered.canonical).toBe(`${S.origin}/blog`)
    const p = headFor({ kind: 'post', status: 200, data: post as never }, S, '/blog/x')
    expect(p.title).toBe(`${(post as { seo: { title: string } }).seo.title} · ${S.name}`)
    expect(headFor({ kind: 'search', status: 200, data: null, q: 'abc', type: 'all' }, S, '/search?q=abc')).toMatchObject({ title: `搜索：abc · ${S.name}`, noindex: true })
    expect(headFor({ kind: '404', status: 404, data: { recent: [] } }, S, '/x?y=1')).toMatchObject({ noindex: true, canonical: `${S.origin}/x` })
  })
})
