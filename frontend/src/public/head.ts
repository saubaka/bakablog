import type { SiteInfo } from '@/shared/types'
import type { PageState } from './state'

/* The <head> the server wrote for the first screen stays as it is. After that every navigation updates the parts a visitor or
   a link-preview can see: title, description, canonical address and the robots flag. The wording mirrors backend/app/seo/spa.py. */

export interface HeadInfo { title: string; description: string; canonical: string; noindex: boolean }

const suffix = (site: SiteInfo, title: string): string => (title ? `${title} · ${site.name}` : site.name)

function pageParam(path: string, page: number): string {
  return page > 1 ? `${path}?page=${page}` : path
}

/** Pure: the head of a page from its state. */
export function headFor(state: PageState, site: SiteInfo, path: string): HeadInfo {
  const fallback = site.seo.description || site.description
  const abs = (p: string): string => `${site.origin}${p}`
  switch (state.kind) {
    case 'home':
      return { title: site.tagline ? `${site.name} · ${site.tagline}` : site.name, description: fallback, canonical: abs('/'), noindex: false }
    case 'blog': {
      const { page } = state.data
      const filtered = !!(state.query.q || state.query.sort !== 'new')
      return {
        title: suffix(site, `博客${page > 1 ? ` · 第 ${page} 页` : ''}`), description: '代码、设计、日常。',
        canonical: abs(filtered ? '/blog' : pageParam('/blog', page)), noindex: filtered,
      }
    }
    case 'taxonomy': {
      const f = state.data.filters
      const row = f.category ?? f.tag ?? f.series
      const name = f.category?.name ?? f.tag?.name ?? f.series?.title ?? ''
      const description = (row && 'description' in row ? row.description : '') || `“${name}”下的文章`
      const base = path.split('?')[0] ?? path
      return { title: suffix(site, `${name}${state.data.page > 1 ? ` · 第 ${state.data.page} 页` : ''}`), description, canonical: abs(pageParam(base, state.data.page)), noindex: state.query.sort !== 'new' }
    }
    case 'post': {
      const seo = state.data.seo
      return { title: suffix(site, seo.title), description: seo.description || fallback, canonical: seo.canonical || abs(state.data.url), noindex: seo.noindex }
    }
    case 'archive': return { title: suffix(site, '归档'), description: '按年月看所有文章。', canonical: abs('/archive'), noindex: false }
    case 'moments': {
      const filtered = !!(state.query.tag || state.query.mood || state.query.month)
      return { title: suffix(site, '动态'), description: '想到什么发什么：一句话、几张照片、一个链接。', canonical: abs('/moments'), noindex: filtered }
    }
    case 'moment': {
      const text = state.data.text || (state.data.media.length ? '（图片）' : state.data.link_card?.title ?? '动态')
      return { title: suffix(site, `${text.slice(0, 40)} · 动态`), description: text.slice(0, 160), canonical: abs(state.data.url), noindex: false }
    }
    case 'page': {
      const seo = state.data.seo
      return { title: suffix(site, seo.title || state.data.title), description: seo.description || state.data.title, canonical: seo.canonical || abs(state.data.url), noindex: seo.noindex }
    }
    case 'search': return { title: suffix(site, state.q ? `搜索：${state.q}` : '搜索'), description: '在文章、动态和页面里找东西。', canonical: abs('/search'), noindex: true }
    case '404': return { title: suffix(site, site.texts.not_found_title), description: site.texts.not_found_text, canonical: abs(path.split('?')[0] ?? path), noindex: true }
    case '500': return { title: suffix(site, site.texts.error_title), description: site.texts.error_text, canonical: abs(path.split('?')[0] ?? path), noindex: true }
  }
}

function meta(name: string, content: string, attr: 'name' | 'property' = 'name'): void {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${name}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, name)
    document.head.append(el)
  }
  el.setAttribute('content', content)
}

function canonicalLink(href: string): void {
  let el = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!el) {
    el = document.createElement('link')
    el.rel = 'canonical'
    document.head.append(el)
  }
  el.href = href
}

export function applyHead(h: HeadInfo): void {
  document.title = h.title
  meta('description', h.description)
  meta('robots', h.noindex ? 'noindex,nofollow' : 'index,follow,max-image-preview:large')
  meta('og:title', h.title, 'property')
  meta('og:description', h.description, 'property')
  meta('og:url', h.canonical, 'property')
  if (h.canonical) canonicalLink(h.canonical)
}
