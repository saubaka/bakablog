import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { __resetFrames } from '@/shared/frame'
import { trackProgress, type ReadProgress } from '@/public/progress'

/* happy-dom has no layout: the page height, the window height and the scroll position are set by hand, and frames are driven by hand. */
let page = 3000
let view = 1000
let scroll = 0
let t = 0
let cbs: FrameRequestCallback[] = []
const frame = (n = 1): void => { for (let i = 0; i < n; i += 1) { const run = cbs; cbs = []; t += 16; run.forEach((cb) => cb(t)) } }

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback): number => { cbs.push(cb); return cbs.length })
  vi.stubGlobal('cancelAnimationFrame', () => { cbs = [] })
  Object.defineProperty(document.documentElement, 'scrollHeight', { configurable: true, get: () => page })
  Object.defineProperty(window, 'innerHeight', { configurable: true, get: () => view })
  Object.defineProperty(window, 'scrollY', { configurable: true, get: () => scroll })
  page = 3000; view = 1000; scroll = 0; t = 0; cbs = []
})
afterEach(() => { __resetFrames(); vi.unstubAllGlobals() })

describe('read progress (how far the thread is stitched)', () => {
  it('raw is how far the page has been scrolled, 0 at the top and 1 at the bottom; what is shown glides after it and lands exactly', () => {
    let last: ReadProgress = { raw: 0, shown: 0, scrollY: 0 }
    const stop = trackProgress((p) => { last = { ...p } })
    frame(2)
    expect(last.raw).toBe(0)
    scroll = 500; window.dispatchEvent(new Event('scroll')); frame()
    expect(last.raw).toBe(0.25)                                     // 500 of the 2000 px that can be scrolled
    expect(last.shown).toBeGreaterThan(0)                            // it has started to follow ...
    expect(last.shown).toBeLessThan(0.25)                            // ... but is not there yet: it glides
    frame(80)
    expect(last.shown).toBe(0.25)
    scroll = 2000; window.dispatchEvent(new Event('scroll')); frame(80)
    expect(last.raw).toBe(1)
    expect(last.shown).toBe(1)
    scroll = 9999; window.dispatchEvent(new Event('scroll')); frame(10)
    expect(last.raw).toBe(1)                                         // an overscroll never goes past the end
    expect(last.scrollY).toBe(9999)
    stop()
  })

  it('a page that does not scroll counts as 0, not as fully read', () => {
    page = 1010                                                      // 10 px of room: not a page anyone scrolls
    scroll = 10
    let last: ReadProgress = { raw: 1, shown: 1, scrollY: 0 }
    const stop = trackProgress((p) => { last = { ...p } })
    frame(2)
    expect(last.raw).toBe(0)
    stop()
  })

  it('a new listener is told where things stand at once; the loop stops by itself when nothing moves any more and when the last listener leaves', () => {
    const seen: number[] = []
    const stop = trackProgress((p) => { seen.push(p.shown) })
    expect(seen.length).toBe(1)
    frame(40)
    cbs.length = 0                                                   // (the settle window after the last wake is real time in a test)
    const n = seen.length
    stop()
    scroll = 800; window.dispatchEvent(new Event('scroll')); frame(5)
    expect(seen.length).toBe(n)                                      // nobody is listening any more
  })
})
