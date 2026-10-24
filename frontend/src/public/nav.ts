import type { NavItem } from '@/shared/types'

/** Which navigation entry a path belongs to: posts, categories, tags and series live under "blog"; a single moment under "moments". */
export function navTarget(path: string): string {
  if (path === '/blog' || path.startsWith('/blog/') || /^\/(category|tag|series)\//.test(path)) return '/blog'
  if (path === '/moments' || path.startsWith('/moments/')) return '/moments'
  return path
}

/** Index of the entry to highlight, or -1. Exact match first; then the entry the path belongs to; then the longest prefix. */
export function currentIndex(items: NavItem[], path: string): number {
  const links = items.map((it, i) => ({ it, i })).filter(({ it }) => it.kind !== 'action' && !it.external && it.url.startsWith('/'))
  const exact = links.find(({ it }) => it.url === path)
  if (exact) return exact.i
  const target = navTarget(path)
  const owner = links.find(({ it }) => it.url === target)
  if (owner) return owner.i
  let best = -1
  let len = 0
  for (const { it, i } of links) {
    if (it.url !== '/' && path.startsWith(`${it.url}/`) && it.url.length > len) { best = i; len = it.url.length }
  }
  return best
}

/** The icon of a navigation entry: its sticker if the sprite has it, otherwise a fitting default. */
export function iconFor(item: NavItem, known: ReadonlySet<string>): string {
  if (item.sticker && known.has(item.sticker)) return item.sticker
  if (item.action === 'search') return 'search'
  if (item.action === 'more') return 'more'
  if (item.action === 'top') return 'arrow-u'
  if (item.url === '/') return 'home'
  if (item.url === '/blog') return 'book'
  if (item.url === '/moments') return 'chat'
  if (item.url === '/archive') return 'calendar'
  if (/\.xml$|^\/feed\//.test(item.url)) return 'rss'
  if (item.kind === 'page') return 'smile'
  return item.external ? 'external' : 'link'
}

/** The page a scroll past the edge leads to: the next (dir 1) or previous (dir -1) entry of the menu that is a page of this site (actions such as "search" and links to
    other sites are skipped). Nothing before the first entry and nothing after the last, and nothing at all when the current page is not in the menu. */
export function adjacentLink(items: NavItem[], path: string, dir: 1 | -1): { item: NavItem; index: number; from: number } | null {
  const pages = items.map((item, index) => ({ item, index })).filter(({ item }) => item.kind !== 'action' && !item.external && item.url.startsWith('/'))
  const here = currentIndex(pages.map((p) => p.item), path)
  if (here < 0) return null
  const next = pages[here + dir]
  return next ? { item: next.item, index: next.index, from: pages[here]?.index ?? 0 } : null
}
