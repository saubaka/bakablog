import { describe, expect, it } from 'vitest'
import { adjacentLink, currentIndex, iconFor, navTarget } from '@/public/nav'
import { isServerPath } from '@/public/router'
import type { NavItem } from '@/shared/types'

const item = (label: string, url: string, patch: Partial<NavItem> = {}): NavItem => ({ id: null, label, kind: 'route', url, action: null, sticker: null, external: false, ...patch })
const top = [item('首页', '/'), item('博客', '/blog'), item('动态', '/moments'), item('归档', '/archive'), item('关于', '/about', { kind: 'page' })]

describe('which navigation entry is current', () => {
  it('exact matches', () => {
    expect(currentIndex(top, '/')).toBe(0)
    expect(currentIndex(top, '/archive')).toBe(3)
    expect(currentIndex(top, '/about')).toBe(4)
  })
  it('posts, categories, tags and series belong to "blog"; one moment belongs to "moments"', () => {
    for (const p of ['/blog/x', '/category/a', '/tag/b', '/series/c']) expect(currentIndex(top, p)).toBe(1)
    expect(currentIndex(top, '/moments/3')).toBe(2)
  })
  it('pages without an entry highlight nothing; the home entry never matches by prefix', () => {
    expect(currentIndex(top, '/search')).toBe(-1)
    expect(currentIndex(top, '/no-such')).toBe(-1)
    expect(currentIndex(top, '/blog-not-really')).toBe(-1)
  })
  it('actions and external links are never current', () => {
    const items = [item('搜索', '', { kind: 'action', action: 'search' }), item('外链', 'https://x.test/blog', { kind: 'link', external: true })]
    expect(currentIndex(items, '/blog')).toBe(-1)
  })
  it('navTarget', () => {
    expect(navTarget('/blog/a')).toBe('/blog')
    expect(navTarget('/moments/9')).toBe('/moments')
    expect(navTarget('/archive')).toBe('/archive')
  })
  it('icons come from the sticker, else from the address', () => {
    const known = new Set(['home', 'star'])
    expect(iconFor(item('x', '/y', { sticker: 'star' }), known)).toBe('star')
    expect(iconFor(item('x', '/y', { sticker: 'nope' }), known)).toBe('link')
    expect(iconFor(item('x', '/blog'), known)).toBe('book')
    expect(iconFor(item('x', '/feed/posts.xml', { kind: 'link' }), known)).toBe('rss')
    expect(iconFor(item('x', '', { kind: 'action', action: 'more' }), known)).toBe('more')
  })
})

describe('server paths are never handled by the router', () => {
  it.each(['/admin', '/admin/posts', '/api/site', '/media/abc/960.webp', '/feed/posts.xml', '/assets/x.js', '/sitemap.xml', '/robots.txt', '/favicon.svg'])('%s', (p) => {
    expect(isServerPath(p)).toBe(true)
  })
  it.each(['/', '/blog', '/blog/admin', '/administrator', '/apiary', '/about', '/moments/3'])('%s is an app page', (p) => {
    expect(isServerPath(p)).toBe(false)
  })
})

describe('the page a scroll past the edge leads to', () => {
  it('the next entry below the last line of a page, the previous one above its first', () => {
    expect(adjacentLink(top, '/blog', 1)?.item.url).toBe('/moments')
    expect(adjacentLink(top, '/blog', -1)?.item.url).toBe('/')
    expect(adjacentLink(top, '/moments', 1)?.item.url).toBe('/archive')
  })

  it('nothing above the first entry and nothing below the last', () => {
    expect(adjacentLink(top, '/', -1)).toBeNull()
    expect(adjacentLink(top, '/about', 1)).toBeNull()
    expect(adjacentLink(top, '/', 1)?.item.url).toBe('/blog')
    expect(adjacentLink(top, '/about', -1)?.item.url).toBe('/archive')
  })

  it('pages that belong to an entry count as that entry (an article is part of the blog)', () => {
    expect(adjacentLink(top, '/blog/some-post', 1)?.item.url).toBe('/moments')
    expect(adjacentLink(top, '/category/code', -1)?.item.url).toBe('/')
    expect(adjacentLink(top, '/moments/12', 1)?.item.url).toBe('/archive')
  })

  it('a page that is not in the menu has no neighbours', () => {
    expect(adjacentLink(top, '/search', 1)).toBeNull()
    expect(adjacentLink(top, '/no-such-page', -1)).toBeNull()
  })

  it('actions and links to other sites are skipped, and the answer says where the bead is in the full list', () => {
    const bar = [item('首页', '/'), item('博客', '/blog'), item('动态', '/moments'), item('搜索', '', { kind: 'action', action: 'search' }), item('更多', '', { kind: 'action', action: 'more' })]
    expect(adjacentLink(bar, '/moments', 1)).toBeNull()                          // after the last page of the bar there is only "search" and "more"
    const mixed = [item('首页', '/'), item('搜索', '', { kind: 'action', action: 'search' }), item('他站', 'https://example.org', { external: true }), item('博客', '/blog')]
    const r = adjacentLink(mixed, '/', 1)
    expect(r?.item.url).toBe('/blog')
    expect(r?.index).toBe(3)
    expect(r?.from).toBe(0)
  })
})
