import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as fx from '@/fx/engine'
import { MAX_DT, MAX_SPEED, MIN_MS, SMOOTH } from '@/fx/math'

/* happy-dom has no layout, so every element gets its box from here (the engine reads offsetTop / offsetHeight / offsetParent). */
function box(top: number, height = 100, attrs: Record<string, string> = {}): HTMLElement {
  const el = document.createElement('div')
  el.dataset.fx = 'rise'
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v)
  Object.defineProperties(el, {
    offsetParent: { value: document.body, configurable: true },
    offsetTop: { value: top, configurable: true },
    offsetHeight: { value: height, configurable: true },
    offsetLeft: { value: 0, configurable: true },
  })
  document.body.append(el)
  return el
}
const frames = async (n = 3): Promise<void> => { for (let i = 0; i < n; i += 1) await new Promise((r) => requestAnimationFrame(() => r(undefined))) }
const num = (el: HTMLElement, name: string): number => Number(el.style.getPropertyValue(name))
let scroll = 0
let clock = 0
/** Runs the engine for `ms` of mocked time, one 16 ms frame at a time. */
async function play(ms: number, each?: () => void): Promise<void> {
  for (let t = 0; t < ms; t += 16) { clock += 16; await frames(1); each?.() }
}

beforeEach(() => {
  // frames run as fast as timers fire; the engine reads the mocked clock, not the real one
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback): number => setTimeout(() => cb(clock), 0) as unknown as number)
  scroll = 0; clock = 1000
  localStorage.clear()
  window.history.replaceState(null, '', '/')
  document.body.innerHTML = ''
  document.documentElement.className = ''
  fx.__reset()
  fx.__setEnv({ now: () => clock, scrollY: () => scroll, viewportHeight: () => 1000 })
})
afterEach(() => { fx.__reset(); document.body.innerHTML = ''; vi.unstubAllGlobals() })

describe('motion engine', () => {
  it('computes the first picture right after registering (before any paint)', async () => {
    fx.init('full')
    const below = box(1800)
    const middle = box(400)
    const above = box(-600)
    ;[below, middle, above].forEach(fx.register)
    await Promise.resolve()                       // the microtask that measures and writes
    expect(below.getAttribute('data-fx-state')).toBe('pre')
    expect(num(below, '--fx-in')).toBe(0)
    expect(above.getAttribute('data-fx-state')).toBe('post')     // behind the viewport: simply there, no entrance
    expect(num(above, '--fx-out')).toBe(1)
    expect(num(middle, '--fx-in')).toBe(0)        // on screen and new: waits for its (quick) entrance instead of popping in ...
    expect(fx.read(middle)).toMatchObject({ intro: true })
    await play(900)
    expect(middle.getAttribute('data-fx-state')).toBe('done')    // ... and ends fully in place
    expect(num(middle, '--fx-in')).toBe(1)
    expect(num(middle, '--fx-out')).toBe(0)
  })

  it('follows the scroll position, both ways, and ends exactly at the right numbers', async () => {
    fx.init('full')
    const el = box(1500)
    fx.register(el)
    await Promise.resolve()
    expect(num(el, '--fx-in')).toBe(0)
    scroll = 800                                  // top edge at 700px of 1000: inside the entering range
    fx.refresh(); await play(MIN_MS + 100)
    const mid = num(el, '--fx-in')
    expect(mid).toBeGreaterThan(0)
    expect(mid).toBeLessThan(1)
    scroll = 1200; fx.refresh(); await play(MIN_MS + 100)
    expect(num(el, '--fx-in')).toBe(1)
    scroll = 800; fx.refresh(); await play(MIN_MS + 100)
    expect(num(el, '--fx-in')).toBe(mid)          // back to the same place: the same picture
  })

  it('a slow scroll is followed closely: it trails by a fraction of a second at most, and lands exactly when the scroll stops', async () => {
    fx.init('full')
    const el = box(1500)
    fx.register(el)
    await Promise.resolve()
    let worst = 0
    for (let y = 400; y <= 1300; y += 5) {        // 5 px per 16 ms frame = 310 px/s, the whole 300 px entering range takes ~1 s
      scroll = y; clock += 16; await frames(1)
      const r = fx.read(el) as { lin: number; tin: number }
      worst = Math.max(worst, Math.abs(r.lin - r.tin))
    }
    expect(worst).toBeGreaterThan(0)              // it is a soft follower, not a copy
    expect(worst).toBeLessThan(1.04 * SMOOTH * 1.6 + 0.01)   // trailing by about speed x SMOOTH (the range is entered at about 1.04 per second)
    await play(600)
    const r = fx.read(el) as { lin: number; tin: number }
    expect(r.lin).toBe(r.tin)
  })

  it('a big jump never pops: the element glides for at least the minimum time, at a limited speed', async () => {
    fx.init('full')
    const el = box(1500)
    fx.register(el)
    await Promise.resolve()
    scroll = 1200                                 // jump: the target is "completely in" at once
    fx.refresh()
    const seen: number[] = []
    await play(MIN_MS * 3, () => seen.push((fx.read(el) as { lin: number }).lin))
    expect(seen[0]).toBeGreaterThan(0)            // it has started moving ...
    expect(seen[0]).toBeLessThan(0.1)             // ... but it is nowhere near done after one frame
    const done = seen.findIndex((v) => v >= 1)
    expect(done).toBeGreaterThan(0)
    expect((done + 1) * 16).toBeGreaterThanOrEqual(MIN_MS - 16)        // a complete change takes at least MIN_MS
    expect((done + 1) * 16).toBeLessThanOrEqual(MIN_MS + 300)          // and not much more (starting and stopping softly adds a little)
    for (let i = 1; i < seen.length; i += 1) {
      expect((seen[i] as number) - (seen[i - 1] as number)).toBeLessThanOrEqual(MAX_SPEED * 0.016 * 1.01)   // never faster than one complete change per MIN_MS
      expect(seen[i]).toBeGreaterThanOrEqual(seen[i - 1] as number)
    }
    expect(num(el, '--fx-in')).toBe(1)
    expect(el.getAttribute('data-fx-state')).toBe('done')
  })

  it('leaving glides too: a fling past an element does not make it vanish at once', async () => {
    fx.init('full')
    const el = box(400)
    fx.register(el)
    await Promise.resolve()
    expect(num(el, '--fx-out')).toBe(0)
    scroll = 2000                                 // the element is far above the screen now
    fx.refresh(); await play(16)
    const early = num(el, '--fx-out')
    expect(early).toBeGreaterThan(0)
    expect(early).toBeLessThan(0.2)
    expect(el.getAttribute('data-fx-state')).toBe('active')
    await play(MIN_MS + 100)
    expect(num(el, '--fx-out')).toBe(1)
    expect(el.getAttribute('data-fx-state')).toBe('post')
  })

  it('reverses smoothly: going back before it finished turns the glide around without a jump', async () => {
    fx.init('full')
    const el = box(1500)
    fx.register(el)
    await Promise.resolve()
    scroll = 1200; fx.refresh(); await play(160)
    const part = (fx.read(el) as { lin: number }).lin
    expect(part).toBeGreaterThan(0.1)
    expect(part).toBeLessThan(0.8)
    scroll = 0; fx.refresh()
    const seen: number[] = [part]
    await play(1200, () => seen.push((fx.read(el) as { lin: number }).lin))
    for (let i = 1; i < seen.length; i += 1) expect(Math.abs((seen[i] as number) - (seen[i - 1] as number))).toBeLessThanOrEqual(MAX_SPEED * 0.016 * 1.01)   // no jump at the turn
    expect(Math.max(...seen)).toBeLessThan(part + 0.12)       // it carries on a little (it has weight) but only a little
    expect(seen[seen.length - 1]).toBe(0)
    expect(num(el, '--fx-in')).toBe(0)
  })

  it('a long gap between frames (hidden tab, long task) does not use up the glide in one step', async () => {
    fx.init('full')
    const el = box(1500)
    fx.register(el)
    await Promise.resolve()
    scroll = 1200; fx.refresh(); await play(16)
    const before = (fx.read(el) as { lin: number }).lin
    clock += 10_000; fx.refresh(); await frames(1)
    const after = (fx.read(el) as { lin: number }).lin
    expect(after - before).toBeLessThanOrEqual(MAX_SPEED * (MAX_DT / 1000) * 1.01)
    expect(after).toBeLessThan(1)
  })

  it('the frame loop sleeps once everything has arrived', async () => {
    fx.init('full')
    const el = box(1500)
    fx.register(el)
    await Promise.resolve()
    scroll = 1200; fx.refresh()
    await play(60)
    expect(fx.stats().moving).toBe(true)
    await play(MIN_MS + 400)
    expect(fx.stats().moving).toBe(false)
    await new Promise((r) => setTimeout(r, 250))  // the settle window after the last scroll is real time (140 ms)
    const n = fx.stats().frames
    await play(200)
    expect(fx.stats().frames).toBe(n)             // no more frames are scheduled
  })

  it('a heading-height element taller than 90% of the screen never leaves', async () => {
    fx.init('full')
    const tall = box(0, 950)
    fx.register(tall)
    scroll = 900; fx.refresh(); await frames()
    expect(num(tall, '--fx-out')).toBe(0)
  })

  it('a focused element is never transparent: it is shown at once, and glides back out when focus leaves', async () => {
    fx.init('full')
    const el = box(1800)
    const link = document.createElement('a')
    link.href = '#'
    el.append(link)
    fx.register(el)
    await Promise.resolve()
    expect(num(el, '--fx-in')).toBe(0)
    link.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
    await play(16)
    expect(num(el, '--fx-in')).toBe(1)            // no glide: it must be readable the moment it has focus
    link.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
    await play(16)
    expect(num(el, '--fx-in')).toBeGreaterThan(0.5)
    await play(MIN_MS + 600)
    expect(num(el, '--fx-in')).toBe(0)
  })

  it('while a page opens at the top everything on its first screen enters, top to bottom, after the head; what is below the fold waits for the scroll', async () => {
    fx.init('full')
    const head = box(100, 60, { 'data-fx-intro': '0' })
    const lead = box(180, 40, { 'data-fx-intro': '1' })
    const first = box(300, 200)
    const second = box(520, 200)
    const third = box(740, 200)
    const far = box(1800, 200)
    ;[far, third, second, first, lead, head].forEach(fx.register)       // registration order must not matter
    await Promise.resolve()
    const start = (el: HTMLElement): number => (fx.read(el) as { intro: boolean }).intro ? 1 : 0
    expect([head, lead, first, second, third].map(start)).toEqual([1, 1, 1, 1, 1])
    expect(fx.read(far)).toMatchObject({ intro: false, state: 'pre' })
    expect([head, lead, first, second, third].map((e) => num(e, '--fx-in'))).toEqual([0, 0, 0, 0, 0])
    const order: HTMLElement[] = []
    await play(1800, () => { for (const e of [head, lead, first, second, third]) if (num(e, '--fx-in') > 0.02 && !order.includes(e)) order.push(e) })
    expect(order).toEqual([head, lead, first, second, third])             // the head first, then the rest down the page
    for (const e of [head, lead, first]) expect(num(e, '--fx-in')).toBe(1)
    expect(num(far, '--fx-in')).toBe(0)
    scroll = 1500; fx.refresh(); await play(MIN_MS + 100)                   // below the fold: the scroll brings it in
    expect(num(far, '--fx-in')).toBe(1)
  })

  it('content that arrives with the head a moment later (the article body) belongs to the same entrance; a page restored by Back / Forward has none', async () => {
    fx.init('full')
    const head = box(100, 60, { 'data-fx-intro': '0' })
    fx.register(head)
    await Promise.resolve()
    const body = box(300, 200)
    clock += 120                                   // a moment later, inside the opening window
    fx.register(body)
    await Promise.resolve()
    expect(fx.read(body)).toMatchObject({ intro: true })
    await play(1800)
    expect(num(body, '--fx-in')).toBe(1)
    // restored at a scroll position: nothing plays
    fx.__reset(); document.body.innerHTML = ''; clock += 5000; scroll = 600
    fx.init('full')
    const head2 = box(700, 60, { 'data-fx-intro': '0' })
    const body2 = box(800, 200)
    ;[head2, body2].forEach(fx.register)
    await Promise.resolve()
    expect(fx.read(head2)).toMatchObject({ intro: false })
    expect(fx.read(body2)).toMatchObject({ intro: false })
    expect(num(body2, '--fx-in')).toBe(1)
  })

  it('content that shows up later on its own (a new filter result, more moments) gets a quick entrance if it is on screen, none if it is below', async () => {
    fx.init('full')
    const head = box(100, 60, { 'data-fx-intro': '0' })
    fx.register(head)
    await Promise.resolve()
    await play(1500)                               // the page has finished opening
    const shown = box(400)
    const hidden = box(1900)
    ;[shown, hidden].forEach(fx.register)
    await Promise.resolve()
    expect(fx.read(shown)).toMatchObject({ intro: true })
    expect(fx.read(hidden)).toMatchObject({ intro: false, state: 'pre' })
    expect(num(shown, '--fx-in')).toBe(0)
    await play(MIN_MS + 400)
    expect(num(shown, '--fx-in')).toBe(1)
  })

  it('switching motion off and on again does not replay anything', async () => {
    fx.init('full')
    const el = box(400)
    fx.register(el)
    await Promise.resolve()
    await play(1500)
    expect(num(el, '--fx-in')).toBe(1)
    fx.setMode('off')
    fx.setMode('full')
    await play(32)
    expect(fx.read(el)).toMatchObject({ intro: false })
    expect(num(el, '--fx-in')).toBe(1)
  })

  it('an element the app focuses itself (tabindex -1, the page title) keeps its entrance', async () => {
    fx.init('full')
    const head = box(100, 60, { 'data-fx-intro': '1', tabindex: '-1' })
    fx.register(head)
    await Promise.resolve()
    expect(num(head, '--fx-in')).toBe(0)
    head.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
    await play(48)
    expect(fx.read(head)).toMatchObject({ forced: false })
    expect(num(head, '--fx-in')).toBeLessThan(0.5)
    await play(140 + 90 + 700 + 100)
    expect(num(head, '--fx-in')).toBe(1)
  })

  it('page heads enter on their own clock when the page opens at the top', async () => {
    fx.init('full')
    const head = box(100, 60, { 'data-fx-intro': '2' })
    fx.register(head)
    await Promise.resolve()
    expect(num(head, '--fx-in')).toBe(0)          // in view, but waiting for its turn
    await play(140 + 2 * 90 + 700 + 100)
    expect(num(head, '--fx-in')).toBe(1)
  })

  it('the intro is decided when the elements are placed, after the app has put the page at its start position', async () => {
    fx.init('full')
    scroll = 700                                  // the OLD page's scroll position when the new page's elements register
    const head = box(100, 60, { 'data-fx-intro': '0' })
    fx.register(head)
    scroll = 0                                    // the app scrolls to the top before the microtask that places the elements runs
    await Promise.resolve()
    expect(fx.read(head)).toMatchObject({ intro: true })
    expect(num(head, '--fx-in')).toBe(0)          // waiting for its turn, then it enters
    await play(140 + 700 + 100)
    expect(num(head, '--fx-in')).toBe(1)
  })

  it('no intro when the page opens scrolled down (back / forward)', async () => {
    fx.init('full')
    scroll = 600
    const head = box(700, 60, { 'data-fx-intro': '0' })
    fx.register(head)
    await Promise.resolve()
    expect(num(head, '--fx-in')).toBe(1)
  })

  it('stagger: neighbours in a row start one after another', async () => {
    fx.init('full')
    const row = document.createElement('div')
    row.setAttribute('data-fx-stagger', '')
    document.body.append(row)
    const cards = [0, 1, 2].map((i) => {
      const c = box(700, 200)
      Object.defineProperty(c, 'offsetLeft', { value: i * 300 })
      row.append(c)
      return c
    })
    cards.forEach(fx.register)
    await Promise.resolve()
    await play(1500)                              // the entrance is over: what is left is the scroll-driven stagger
    const v = cards.map((c) => num(c, '--fx-in'))
    expect(v[0]).toBeGreaterThan(v[1] as number)
    expect(v[1]).toBeGreaterThan(v[2] as number)
  })

  it('unregistering forgets the element (a page that was replaced)', async () => {
    fx.init('full')
    const el = box(400)
    fx.register(el)
    await Promise.resolve()
    expect(fx.read(el)).not.toBeNull()
    fx.unregister(el)
    expect(fx.read(el)).toBeNull()
    expect(fx.stats().items).toBe(0)
  })

  it('off: nothing is written, the guard is lifted, and switching back on works', async () => {
    document.documentElement.classList.add('fx-pending')
    localStorage.setItem('bb:motion', 'off')
    fx.init('full')
    expect(document.documentElement.classList.contains('fx-off')).toBe(true)
    expect(document.documentElement.classList.contains('fx-pending')).toBe(false)
    const el = box(1800)
    fx.register(el)
    await Promise.resolve()
    expect(el.style.getPropertyValue('--fx-in')).toBe('')
    fx.setMode('full')
    await play(32)
    expect(document.documentElement.classList.contains('fx-off')).toBe(false)
    expect(num(el, '--fx-in')).toBe(0)
    expect(el.getAttribute('data-fx-state')).toBe('pre')
    fx.setMode('off')
    expect(el.style.getPropertyValue('--fx-in')).toBe('')
    expect(el.hasAttribute('data-fx-state')).toBe(false)
    expect(localStorage.getItem('bb:motion')).toBe('off')
  })

  it('an element that is not displayed is left alone', async () => {
    fx.init('full')
    const el = box(400)
    Object.defineProperty(el, 'offsetParent', { value: null })
    fx.register(el)
    await Promise.resolve()
    expect(fx.read(el)).toMatchObject({ hidden: true })
    expect(el.style.getPropertyValue('--fx-in')).toBe('')
  })

  it('pop elements alternate their tilt', () => {
    fx.init('full')
    const a = box(400, 50, {}); a.dataset.fx = 'pop'
    const b = box(500, 50, {}); b.dataset.fx = 'pop'
    fx.register(a); fx.register(b)
    expect(a.style.getPropertyValue('--fx-rot')).not.toBe(b.style.getPropertyValue('--fx-rot'))
  })
})
