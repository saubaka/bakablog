import { shallowRef } from 'vue'
import type {
  Archive, BootData, HomePayload, Moment, MomentsPage, PageDetail, PostDetail, PostsPage, SearchResult, SiteInfo, Taxonomy,
} from '@/shared/types'

/* What the page on screen is made of. The router loads it before the navigation completes (data.ts), so a page component
   never has to show "loading": when it renders, its data is there. */

export interface MomentsQuery { tag: string; mood: string; month: string }
export interface BlogQuery { page: number; q: string; sort: 'new' | 'old' | 'views' }
export type TaxonomyKind = 'category' | 'tag' | 'series'

export type PageState =
  | { kind: 'home'; status: number; data: HomePayload }
  | { kind: 'blog'; status: number; data: PostsPage; taxonomy: Taxonomy | null; query: BlogQuery }
  | { kind: 'taxonomy'; status: number; data: PostsPage; taxonomy: Taxonomy | null; query: BlogQuery; tax: TaxonomyKind }
  | { kind: 'post'; status: number; data: PostDetail }
  | { kind: 'archive'; status: number; data: Archive }
  | { kind: 'moments'; status: number; data: MomentsPage; query: MomentsQuery }
  | { kind: 'moment'; status: number; data: Moment }
  | { kind: 'page'; status: number; data: PageDetail }
  | { kind: 'search'; status: number; data: SearchResult | null; q: string; type: SearchResult['type'] }
  | { kind: '404'; status: number; data: { recent: PostsPage['items'] } }
  | { kind: '500'; status: number; data: { message: string } }

/** The site settings (name, navigation, theme ...). Replaced as a whole, never edited in place. */
export const site = shallowRef<SiteInfo>(emptySite())
/** The page being shown. Written by the router after a navigation has completed. */
export const page = shallowRef<PageState | null>(null)
/** True when a navigation has been waiting for its data long enough that the visitor should see a sign of life. */
export const loading = shallowRef(false)

export function setSite(next: SiteInfo): void { site.value = next }
export function setPage(next: PageState): void { page.value = next }

/** The server's first-screen JSON, read once; reading it a second time yields nothing (back to the first address fetches normally). */
let boot: BootData | null | undefined
export function takeBootData(): BootData | null {
  if (boot !== undefined) return null
  boot = null
  const el = document.getElementById('bb-data')
  if (!el) return null
  try {
    boot = JSON.parse(el.textContent || 'null') as BootData | null
  } catch {
    boot = null
  }
  el.remove()
  return boot
}

/** Never used for display: only keeps `site.value` typed before the real settings arrive. */
function emptySite(): SiteInfo {
  return {
    name: '', name_en: '', tagline: '', description: '', language: 'zh-CN', timezone: 'Asia/Shanghai', logo: null, favicon: null,
    author: { name: '', bio: '', avatar: null, links: [] }, theme: 'default', decor: { tape: true, doodles: true },
    motion: 'full', code_theme: 'frost', texts: { not_found_title: '', not_found_text: '', error_title: '', error_text: '' },
    seo: { title: '', description: '', keywords: [], share_image: null }, footer: { icp: '', copyright: '', text: '' },
    nav: { top: [], mobile: [], footer: [] }, features: { stats: true, search: true, rss: true }, moods: [], origin: '', version: '', build: '', site_version: 0,
  }
}
