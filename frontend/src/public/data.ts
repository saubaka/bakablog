import type { LocationQuery, RouteLocationNormalized } from 'vue-router'
import { ApiError, getJSON, type Query } from '@/shared/api'
import type {
  Archive, BootData, HomePayload, Moment, MomentsPage, PageDetail, PostDetail, PostsPage, SearchResult, SiteInfo, Taxonomy,
} from '@/shared/types'
import type { BlogQuery, MomentsQuery, PageState, TaxonomyKind } from './state'

/** Cards per page: nine fill the card grid in whole rows (1 + 2 + 3 + 2 + 1). */
export const PER_PAGE = 9

const first = (v: LocationQuery[string] | undefined): string => (Array.isArray(v) ? v[0] ?? '' : v ?? '') || ''

/* ---- query strings ------------------------------------------------------------------------------------------------------------ */
export function blogQuery(q: LocationQuery): BlogQuery {
  const page = Number.parseInt(first(q.page), 10)
  const sort = first(q.sort)
  return {
    page: Number.isFinite(page) && page >= 1 ? Math.min(page, 10000) : 1,
    q: first(q.q).trim().slice(0, 100),
    sort: sort === 'old' || sort === 'views' ? sort : 'new',
  }
}

export function momentsQuery(q: LocationQuery): MomentsQuery {
  const month = first(q.month)
  return { tag: first(q.tag).slice(0, 80), mood: first(q.mood).slice(0, 16), month: /^\d{4}-(0[1-9]|1[0-2])$/.test(month) ? month : '' }
}

/** The /api/posts parameters for a list page. Server and client read the same query string, so a shared link shows the same list. */
export function postsParams(query: BlogQuery, scope: { category?: string; tag?: string; series?: string } = {}): Query {
  return { page: query.page > 1 ? query.page : null, per: PER_PAGE, q: query.q || null, sort: query.sort === 'new' ? null : query.sort, ...scope }
}

/* ---- site -------------------------------------------------------------------------------------------------------------------- */
export const fetchSite = (signal?: AbortSignal): Promise<SiteInfo> => getJSON<SiteInfo>('/api/site', signal ? { signal } : {})

/* ---- taxonomy (category tabs and tag chips): short-lived cache, the server answers repeats with 304 anyway ----------------------- */
let taxCache: { at: number; value: Taxonomy } | null = null
export async function fetchTaxonomy(signal?: AbortSignal): Promise<Taxonomy> {
  if (taxCache && Date.now() - taxCache.at < 30_000) return taxCache.value
  const value = await getJSON<Taxonomy>('/api/taxonomy', signal ? { signal } : {})
  taxCache = { at: Date.now(), value }
  return value
}
export function primeTaxonomy(value: Taxonomy): void { taxCache = { at: Date.now(), value } }

/* ---- more of a list ---------------------------------------------------------------------------------------------------------- */
export function fetchMoments(query: MomentsQuery, cursor: string | null, signal?: AbortSignal): Promise<MomentsPage> {
  return getJSON<MomentsPage>('/api/moments', { query: { tag: query.tag, mood: query.mood, month: query.month, cursor, limit: 10 }, ...(signal ? { signal } : {}) })
}

export function fetchSearch(q: string, type: SearchResult['type'], signal?: AbortSignal): Promise<SearchResult> {
  return getJSON<SearchResult>('/api/search', { query: { q, type: type === 'all' ? null : type }, ...(signal ? { signal } : {}) })
}

export function fetchLatest(per: number, signal?: AbortSignal): Promise<PostsPage> {
  return getJSON<PostsPage>('/api/posts', { query: { per }, ...(signal ? { signal } : {}) })
}

/* ---- the route -> page state mapping ---------------------------------------------------------------------------------------------- */
export interface Redirect { redirect: string }

const KIND_OF_ROUTE: Record<string, BootData['kind']> = {
  home: 'home', blog: 'blog', category: 'taxonomy', tag: 'taxonomy', series: 'taxonomy', post: 'post', archive: 'archive',
  moments: 'moments', moment: 'moment', search: 'search', page: 'page',
}

function param(to: RouteLocationNormalized, key: string): string {
  const v = to.params[key]
  return (Array.isArray(v) ? v[0] : v) ?? ''
}

/** The server inlined this address's data and it is still the address being opened: use it, no request. */
function fromBoot(to: RouteLocationNormalized, boot: BootData): PageState | null {
  const name = String(to.name ?? '')
  if (boot.path !== to.path) return null
  if (boot.kind === '404') return { kind: '404', status: 404, data: { recent: (boot.data as { recent?: PostsPage['items'] }).recent ?? [] } }
  if (KIND_OF_ROUTE[name] !== boot.kind) return null
  const extra = boot as BootData & { taxonomy?: Taxonomy }
  switch (boot.kind) {
    case 'home': return { kind: 'home', status: boot.status, data: boot.data as HomePayload }
    case 'blog': return { kind: 'blog', status: boot.status, data: boot.data as PostsPage, taxonomy: extra.taxonomy ?? null, query: blogQuery(to.query) }
    case 'taxonomy': return { kind: 'taxonomy', status: boot.status, data: boot.data as PostsPage, taxonomy: extra.taxonomy ?? null, query: blogQuery(to.query), tax: name as TaxonomyKind }
    case 'post': return { kind: 'post', status: boot.status, data: boot.data as PostDetail }
    case 'archive': return { kind: 'archive', status: boot.status, data: boot.data as Archive }
    case 'moments': return { kind: 'moments', status: boot.status, data: boot.data as MomentsPage, query: momentsQuery(to.query) }
    case 'moment': return { kind: 'moment', status: boot.status, data: boot.data as Moment }
    case 'page': return { kind: 'page', status: boot.status, data: boot.data as PageDetail }
    default: return null
  }
}

async function notFound(signal?: AbortSignal): Promise<PageState> {
  let recent: PostsPage['items'] = []
  try { recent = (await fetchLatest(3, signal)).items } catch { /* the 404 page works without suggestions */ }
  return { kind: '404', status: 404, data: { recent } }
}

async function fetchRoute(to: RouteLocationNormalized, signal: AbortSignal): Promise<PageState> {
  const name = String(to.name ?? '')
  const opts = { signal }
  switch (name) {
    case 'home': return { kind: 'home', status: 200, data: await getJSON<HomePayload>('/api/home', opts) }
    case 'blog': {
      const query = blogQuery(to.query)
      const scope = { category: first(to.query.category), tag: first(to.query.tag), series: first(to.query.series) }
      const [data, taxonomy] = await Promise.all([getJSON<PostsPage>('/api/posts', { query: postsParams(query, scope), signal }), fetchTaxonomy(signal)])
      return { kind: 'blog', status: 200, data, taxonomy, query }
    }
    case 'category': case 'tag': case 'series': {
      const query = blogQuery(to.query)
      const scope = { [name]: param(to, 'slug') }
      const [data, taxonomy] = await Promise.all([
        getJSON<PostsPage>('/api/posts', { query: postsParams({ ...query, q: '' }, scope), signal }), fetchTaxonomy(signal),
      ])
      return { kind: 'taxonomy', status: 200, data, taxonomy, query: { ...query, q: '' }, tax: name }
    }
    case 'post': {
      const preview = first(to.query.preview)
      return { kind: 'post', status: 200, data: await getJSON<PostDetail>(`/api/posts/${encodeURIComponent(param(to, 'slug'))}`, { query: { preview: preview || null }, signal }) }
    }
    case 'archive': return { kind: 'archive', status: 200, data: await getJSON<Archive>('/api/archive', opts) }
    case 'moments': {
      const query = momentsQuery(to.query)
      return { kind: 'moments', status: 200, data: await fetchMoments(query, null, signal), query }
    }
    case 'moment': return { kind: 'moment', status: 200, data: await getJSON<Moment>(`/api/moments/${param(to, 'id')}`, opts) }
    case 'page': return { kind: 'page', status: 200, data: await getJSON<PageDetail>(`/api/pages/${encodeURIComponent(param(to, 'slug'))}`, opts) }
    case 'search': {
      const q = first(to.query.q).trim().slice(0, 100)
      const t = first(to.query.type)
      const type = t === 'post' || t === 'moment' || t === 'page' ? t : 'all'
      return { kind: 'search', status: 200, data: q ? await fetchSearch(q, type, signal) : null, q, type }
    }
    default: return notFound(signal)
  }
}

/** Everything a navigation needs before the page can be drawn. A renamed address comes back as a redirect; a missing one as the 404 page. */
export async function loadRoute(to: RouteLocationNormalized, signal: AbortSignal, boot: BootData | null): Promise<PageState | Redirect> {
  if (boot) {
    const inline = fromBoot(to, boot)
    if (inline) {
      const extra = boot as BootData & { taxonomy?: Taxonomy }
      if (extra.taxonomy) primeTaxonomy(extra.taxonomy)
      if ((inline.kind === 'blog' || inline.kind === 'taxonomy') && !inline.taxonomy) inline.taxonomy = await fetchTaxonomy(signal).catch(() => null)
      return inline
    }
  }
  try {
    return await fetchRoute(to, signal)
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.moved && err.location) return { redirect: err.location }
      if (err.notFound) return notFound(signal)
    }
    throw err
  }
}

export const isRedirect = (r: PageState | Redirect): r is Redirect => 'redirect' in r
