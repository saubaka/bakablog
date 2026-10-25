import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import FxText from '@/fx/FxText.vue'
import Phrase from '@/fx/Phrase'
import { vFx } from '@/fx/directive'
import NavLink from '@/ui/components/NavLink.vue'
import Pager from '@/public/components/Pager.vue'
import PostCardView from '@/public/components/PostCardView.vue'
import { setSite } from '@/public/state'
import { copyText } from '@/shared/clipboard'
import type { PostCard, SiteInfo } from '@/shared/types'
import site from '@samples/site.json'

const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { render: () => null } }] })
const plugins = [router]
setSite(site as unknown as SiteInfo)
const card = (patch: Partial<PostCard> = {}): PostCard => ({
  id: 1, slug: 'a', url: '/blog/a', title: '一篇文章', summary: '摘要', cover: null, cover_alt: '', cover_focus: { x: 0.5, y: 0.5 }, category: { id: 1, slug: 'c', name: '代码', description: '', sticker: null, url: '/category/c' },
  tags: [{ id: 1, slug: 't', name: 'SQLite', color: 'sky', sticker: null, url: '/tag/t' }], series: null, pinned: false, featured: false, card_style: 'auto',
  published_at: '2026-10-18T09:00:00Z', updated_at: '2026-10-18T09:00:00Z', reading_minutes: 8, word_count: 900, ...patch,
})

describe('FxText', () => {
  it('splits a short heading into words and characters, with one aria-label and hidden pieces', () => {
    const w = mount(FxText, { props: { tag: 'h1', text: '我是 sau_baka' } })
    const h = w.get('h1')
    expect(h.attributes('data-fx')).toBe('text')
    expect(h.attributes('aria-label')).toBe('我是 sau_baka')
    expect(h.findAll('.fx-c').length).toBe('我是sau_baka'.length)
    expect(h.findAll('.fx-w').every((e) => e.attributes('aria-hidden') === 'true')).toBe(true)
    expect(h.text().replace(/\s+/g, '')).toBe('我是sau_baka')
  })
  it('character offsets rise from 0 to the spread, in reading order', () => {
    const w = mount(FxText, { props: { tag: 'h2', text: '今天的云像猫' } })
    const offs = w.findAll('.fx-c').map((c) => Number((c.element as HTMLElement).style.getPropertyValue('--co')))
    expect(offs[0]).toBe(0)
    expect(offs[offs.length - 1]).toBe(0.6)
    expect([...offs].sort((a, b) => a - b)).toEqual(offs)
  })
  it('a long heading is one block that fades; nothing is split', () => {
    const w = mount(FxText, { props: { tag: 'h2', text: '这是一个非常非常非常非常非常非常非常非常非常长的标题用来测试不拆分的情况' } })
    expect(w.get('h2').attributes('data-fx')).toBe('fade')
    expect(w.findAll('.fx-c').length).toBe(0)
    expect(w.get('h2').attributes('aria-label')).toBeUndefined()
  })
  it('lines are joined by line breaks, and the last one carries the marker', () => {
    const w = mount(FxText, { props: { tag: 'h1', lines: ['我是 sau_baka，', '不是笨蛋！！'], highlightLast: true } })
    expect(w.findAll('br').length).toBe(1)
    expect(w.get('em.hl').text()).toBe('不是笨蛋！！')
    expect(w.get('h1').attributes('aria-label')).toBe('我是 sau_baka， 不是笨蛋！！')
  })
  it('a changed sentence is a new element (the engine measures it again)', async () => {
    const w = mount(FxText, { props: { tag: 'h2', text: '第一句' } })
    const first = w.get('h2').element
    await w.setProps({ text: '第二句' })
    expect(w.get('h2').element).not.toBe(first)
  })
})

describe('Phrase', () => {
  it('wraps words so lines break between them, and puts break opportunities between neighbours only', () => {
    const w = mount(Phrase, { props: { text: '差点把自己的数据弄丢' } })
    const words = w.findAll('.ph').map((e) => e.text())
    expect(words.join('')).toBe('差点把自己的数据弄丢')
    expect(w.findAll('wbr').length).toBe(words.length - 1)
  })
  it('leaves a long unbroken run alone', () => {
    const w = mount(Phrase, { props: { text: 'Supercalifragilisticexpialidocious' } })
    expect(w.findAll('.ph').length).toBe(0)
    expect(w.text()).toBe('Supercalifragilisticexpialidocious')
  })
})

describe('NavLink', () => {
  const link = (to: string, props: Record<string, unknown> = {}) => mount(NavLink, { props: { to, ...props }, slots: { default: 'x' }, global: { plugins } })
  it('internal addresses are router links; the sitemap, mail, other sites and the admin are plain links', () => {
    expect(link('/blog').get('a').attributes('href')).toBe('/blog')
    expect(link('/sitemap.xml').get('a').attributes('href')).toBe('/sitemap.xml')
    expect(link('/admin').get('a').attributes('target')).toBeUndefined()
    expect(link('mailto:a@b.c').get('a').attributes('href')).toBe('mailto:a@b.c')
    const ext = link('https://example.com/x', { external: true }).get('a')
    expect(ext.attributes('target')).toBe('_blank')
    expect(ext.attributes('rel')).toBe('noopener noreferrer')
  })
  it('current gets aria-current="page"', () => {
    expect(link('/blog', { current: true }).get('a').attributes('aria-current')).toBe('page')
    expect(link('/blog').get('a').attributes('aria-current')).toBeUndefined()
  })
})

describe('Pager', () => {
  const items = (page: number, pages: number) => mount(Pager, { props: { page, pages, to: (n: number) => `/blog?page=${n}` }, global: { plugins } })
    .findAll('.pager > *').map((e) => (e.classes().includes('is-gap') ? '…' : e.attributes('aria-label')?.includes('页') && !/^第/.test(e.attributes('aria-label') ?? '') ? (e.attributes('aria-label') === '上一页' ? '<' : '>') : e.text()))
  it('shows the first, last and neighbours with gaps', () => {
    expect(items(1, 12)).toEqual(['1', '2', '3', '4', '…', '12', '>'])
    expect(items(6, 12)).toEqual(['<', '1', '…', '5', '6', '7', '…', '12', '>'])
    expect(items(12, 12)).toEqual(['<', '1', '…', '9', '10', '11', '12'])
  })
  it('a single page shows nothing', () => {
    expect(mount(Pager, { props: { page: 1, pages: 1, to: () => '/' }, global: { plugins } }).find('.pager').exists()).toBe(false)
  })
  it('marks the current page', () => {
    const w = mount(Pager, { props: { page: 3, pages: 5, to: (n: number) => `/blog?page=${n}` }, global: { plugins } })
    expect(w.get('[aria-current="page"]').text()).toBe('3')
  })
})

describe('PostCardView', () => {
  const view = (layout: 'side' | 'cover' | 'note' | 'quote' | 'short', patch: Partial<PostCard> = {}) =>
    mount(PostCardView, { props: { post: card(patch), layout }, global: { plugins, directives: { fx: vFx } } })
  it('is one link to the post, with no link nested inside it', () => {
    const w = view('cover')
    expect(w.element.tagName).toBe('A')
    expect(w.element.getAttribute('href')).toBe('/blog/a')
    expect(w.element.querySelectorAll('a').length).toBe(0)
  })
  it('a side card for a featured post carries the badge; a post without a picture gets a generated cover', () => {
    const w = view('side', { featured: true })
    expect(w.find('.badge').text()).toContain('精选')
    expect(w.find('.cover').classes().join(' ')).toMatch(/cv-(sky|rose|mist|paper)/)
  })
  it('note has a tape, quote has a quotation mark and no summary', () => {
    expect(view('note').find('.tape').exists()).toBe(true)
    const q = view('quote')
    expect(q.find('.qmark').exists()).toBe(true)
    expect(q.find('.card__sum').exists()).toBe(false)
  })
  it('the date is the site time zone date', () => {
    expect(view('cover').find('time').text()).toBe('2026.10.18')
  })
})

describe('copyText', () => {
  it('uses the clipboard when it answers', async () => {
    let got = ''
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: async (t: string) => { got = t } }, configurable: true })
    expect(await copyText('abc')).toBe(true)
    expect(got).toBe('abc')
  })
  it('does not hang when the clipboard never answers: falls back after a short wait', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: () => new Promise(() => undefined) }, configurable: true })
    document.execCommand = () => true
    const t0 = Date.now()
    expect(await copyText('abc')).toBe(true)
    expect(Date.now() - t0).toBeLessThan(2000)
  })
  it('reports failure when nothing works', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: async () => { throw new Error('denied') } }, configurable: true })
    document.execCommand = () => false
    expect(await copyText('abc')).toBe(false)
  })
})
