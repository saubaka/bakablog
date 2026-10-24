import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import { ago, bytes, duration, fromLocalInput, toLocalInput, when } from '@/admin/format'
import { actionLabel, todoText } from '@/admin/labels'
import { ALL_ENTRIES, entryFor, NAV, TABBAR } from '@/admin/nav'
import { routes } from '@/admin/router'
import { BLOCKS, defaultConfig, DOODLES, META } from '@/admin/pages/home/blocks'
import { move } from '@/admin/ui/sortable'
import { useRouteQuery } from '@/admin/use'
import { isPreviewMessage, isPreviewReady, PREVIEW_PATH } from '@/preview/protocol'
import { labelTasks, markScrollable } from '@/shared/prose'

const sample = (name: string): Record<string, any> => JSON.parse(readFileSync(join(process.cwd(), '../docs/api-samples/admin', name), 'utf8'))   // eslint-disable-line @typescript-eslint/no-explicit-any

describe('formatting', () => {
  it('sizes', () => {
    expect(bytes(null)).toBe('—')
    expect(bytes(0)).toBe('0 B')
    expect(bytes(1023)).toBe('1023 B')
    expect(bytes(1536)).toBe('1.5 KB')
    expect(bytes(5 * 1024 * 1024)).toBe('5.0 MB')
    expect(bytes(250 * 1024 * 1024)).toBe('250 MB')
  })
  it('durations', () => {
    expect(duration(59)).toBe('0 分钟')
    expect(duration(3 * 3600 + 120)).toBe('3 小时 2 分钟')
    expect(duration(2 * 86400 + 3600)).toBe('2 天 1 小时')
  })
  it('"ago" speaks in the nearest unit and falls back to the date', () => {
    const now = new Date('2026-10-23T12:00:00Z')
    expect(ago('2026-10-23T11:59:50Z', now)).toBe('刚刚')
    expect(ago('2026-10-23T11:30:00Z', now)).toBe('30 分钟前')
    expect(ago('2026-10-23T07:00:00Z', now)).toBe('5 小时前')
    expect(ago('2026-10-20T12:00:00Z', now)).toBe('3 天前')
    expect(ago('2026-09-01T12:00:00Z', now)).toMatch(/^2026-09-0[12]$/)
    expect(ago('2026-10-24T12:00:00Z', now)).toContain('将来')
    expect(ago(null)).toBe('—')
    expect(ago('not a date')).toBe('—')
    expect(when('nonsense')).toBe('—')
  })
  it('a datetime-local value round-trips through UTC without drifting', () => {
    const iso = '2026-10-23T05:47:00.000Z'
    expect(fromLocalInput(toLocalInput(iso))).toBe(iso)
    expect(toLocalInput('')).toBe('')
    expect(fromLocalInput('')).toBeNull()
    expect(fromLocalInput('garbage')).toBeNull()
  })
  it('every audit action the server records has words, and unknown ones are shown as they are', () => {
    const logged = new Set<string>(sample('audit.json').items.map((a: { action: string }) => a.action))
    for (const a of logged) expect(actionLabel(a), a).not.toBe(a)
    expect(actionLabel('something.new')).toBe('something.new')
    expect(todoText({ kind: 'missing_cover', title: '云' })).toContain('云')
    expect(todoText({ kind: 'image_no_alt', count: 3 })).toContain('3')
  })
})

describe('sortable move', () => {
  it('moves one item and leaves the original alone', () => {
    const a = ['a', 'b', 'c', 'd']
    expect(move(a, 0, 2)).toEqual(['b', 'c', 'a', 'd'])
    expect(move(a, 3, 0)).toEqual(['d', 'a', 'b', 'c'])
    expect(a).toEqual(['a', 'b', 'c', 'd'])
  })
  it('out-of-range or no-op moves return the same list', () => {
    const a = ['a', 'b']
    expect(move(a, 0, 0)).toBe(a)
    expect(move(a, -1, 1)).toBe(a)
    expect(move(a, 0, 2)).toBe(a)
  })
})

describe('admin navigation', () => {
  it('every sidebar entry has a route, no address appears twice, and the sidebar covers all pages but the open ones', () => {
    const paths = ALL_ENTRIES.map((e) => e.to)
    expect(new Set(paths).size).toBe(paths.length)
    const routed = new Set(routes.map((r) => r.path))
    for (const p of paths) expect(routed.has(p), p).toBe(true)
    const named = routes.filter((r) => !r.meta?.open && !/[:(]/.test(r.path) && r.path !== '/posts/new' && r.path !== '/pages/new').map((r) => r.path)
    for (const p of named) expect(paths, `sidebar lacks ${p}`).toContain(p)
    expect(NAV.length).toBeGreaterThan(3)
  })
  it('a detail page highlights the list it belongs to', () => {
    expect(entryFor('/posts/12')?.to).toBe('/posts')
    expect(entryFor('/pages/new')?.to).toBe('/pages')
    expect(entryFor('/')?.to).toBe('/')
    expect(entryFor('/nowhere')).toBeNull()
  })
  it('the phone bar has four places that exist', () => {
    expect(TABBAR).toHaveLength(4)
    for (const t of TABBAR) expect(ALL_ENTRIES.some((e) => e.to === t.to)).toBe(true)
  })
  it('every route has a title (the tab name and the screen-reader announcement)', () => {
    for (const r of routes) expect(r.meta?.title, r.path).toBeTruthy()
  })
})

describe('home modules', () => {
  const vocab = sample('settings.json').vocab
  it('the form knows exactly the modules the server accepts', () => {
    expect(BLOCKS.map((b) => b.type).sort()).toEqual([...vocab.home_block_types].sort())
    for (const b of BLOCKS) expect(META[b.type]).toBe(b)
  })
  it('a starting value exists for every module, and the default layout from the server has the same shape', () => {
    for (const b of BLOCKS) expect(Object.keys(defaultConfig(b.type)).length, b.type).toBeGreaterThan(0)
    const served = sample('home.json').blocks as { type: string; config: Record<string, unknown> }[]
    for (const s of served) expect(Object.keys(defaultConfig(s.type)).sort(), s.type).toEqual(Object.keys(s.config).sort())
  })
  it('the doodle choices are the ones the server accepts', () => {
    const served = (sample('home.json').blocks as { type: string; config: { doodles?: string[] } }[]).find((b) => b.type === 'hero')?.config.doodles ?? []
    for (const d of served) expect(DOODLES.map((x) => x.value)).toContain(d)
  })
})

describe('preview frame protocol', () => {
  it('recognises only its own messages', () => {
    expect(isPreviewMessage({ type: 'bb-preview', site: {}, home: [] })).toBe(true)
    expect(isPreviewMessage({ type: 'other' })).toBe(false)
    expect(isPreviewMessage(null)).toBe(false)
    expect(isPreviewMessage('bb-preview')).toBe(false)
    expect(isPreviewReady({ type: 'bb-preview-ready' })).toBe(true)
    expect(isPreviewReady({ type: 'bb-preview' })).toBe(false)
  })
  it('the frame lives under /admin/ (the server only lets that one page be framed)', () => {
    expect(PREVIEW_PATH).toBe('/admin/preview-frame')
  })
})

describe('article HTML accessibility fixes', () => {
  it('a task checkbox is named by its item text', () => {
    const box = document.createElement('div')
    box.innerHTML = '<ul><li><input type="checkbox" class="task-list-item-checkbox"> 买牛奶</li><li><input type="checkbox" class="task-list-item-checkbox"></li></ul>'
    labelTasks(box)
    const [a, b] = [...box.querySelectorAll('input')]
    expect(a?.getAttribute('aria-label')).toBe('买牛奶')
    expect(b?.getAttribute('aria-label')).toBe('任务')
  })
  it('only a block that really scrolls sideways becomes a keyboard stop', () => {
    const box = document.createElement('div')
    box.innerHTML = '<pre id="wide">x</pre><pre id="narrow">y</pre><div class="table-wrap" id="t">z</div>'
    const set = (id: string, scroll: number, client: number): void => {
      const el = box.querySelector(`#${id}`) as HTMLElement
      Object.defineProperty(el, 'scrollWidth', { value: scroll, configurable: true })
      Object.defineProperty(el, 'clientWidth', { value: client, configurable: true })
    }
    set('wide', 900, 300); set('narrow', 300, 300); set('t', 700, 320)
    markScrollable(box)
    expect((box.querySelector('#wide') as HTMLElement).tabIndex).toBe(0)
    expect(box.querySelector('#wide')?.getAttribute('aria-label')).toContain('代码')
    expect(box.querySelector('#narrow')?.hasAttribute('tabindex')).toBe(false)
    expect(box.querySelector('#t')?.getAttribute('aria-label')).toContain('表格')
    set('wide', 300, 300)                       // the window grew: the stop goes away again
    markScrollable(box)
    expect(box.querySelector('#wide')?.hasAttribute('tabindex')).toBe(false)
  })
})

describe('filters that live in the address', () => {
  it('reads defaults, writes only what differs, and goes back to page 1 when a filter changes', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/posts', component: { render: () => null } }] })
    await router.push('/posts?status=draft&page=3')
    let api!: ReturnType<typeof useRouteQuery<{ status: string; q: string; page: string }>>
    const C = defineComponent({ setup() { api = useRouteQuery({ status: 'all', q: '', page: '1' }); return () => h('div') } })
    mount(C, { global: { plugins: [router] } })
    expect(api.state.value).toEqual({ status: 'draft', q: '', page: '3' })
    api.set({ q: '云' })
    await router.isReady()
    await new Promise((r) => setTimeout(r, 0))
    expect(router.currentRoute.value.query).toEqual({ status: 'draft', q: '云' })     // page went back to the default 1, so it is not written
    api.set({ page: '2' })
    await new Promise((r) => setTimeout(r, 0))
    expect(router.currentRoute.value.query).toEqual({ status: 'draft', q: '云', page: '2' })
    api.set({ status: 'all' })
    await new Promise((r) => setTimeout(r, 0))
    expect(router.currentRoute.value.query).toEqual({ q: '云' })
  })
})
