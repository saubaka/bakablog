import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { isAtRest, rubber, spring, stepSpring, unrubber } from '@/shared/spring'

const run = (from: number, to: number, o = {}, seconds = 3): { xs: number[]; end: { x: number; v: number } } => {
  let s = { x: from, v: (o as { velocity?: number }).velocity ?? 0 }
  const xs: number[] = []
  for (let t = 0; t < seconds * 60; t += 1) { s = stepSpring(s, to, 1 / 60, o); xs.push(s.x) }
  return { xs, end: s }
}

describe('spring', () => {
  it('settles on the target, from any starting speed', () => {
    for (const v of [0, 900, -900]) {
      const { end } = run(100, 0, { stiffness: 200, damping: 24, velocity: v })
      expect(isAtRest(end, 0, 0.5)).toBe(true)
    }
  })

  it('a well damped spring does not overshoot; an under-damped one does, a little, and comes back', () => {
    const calm = run(100, 0, { stiffness: 170, damping: 30 })
    expect(Math.min(...calm.xs)).toBeGreaterThanOrEqual(-0.01)
    const lively = run(100, 0, { stiffness: 190, damping: 23 })
    const under = Math.min(...lively.xs)
    expect(under).toBeLessThan(-0.5)
    expect(under).toBeGreaterThan(-12)             // a few percent of the distance, not a bounce
    expect(Math.abs(lively.end.x)).toBeLessThan(0.5)
  })

  it('keeps the speed it was given: thrown towards the target it gets there sooner than from a standstill', () => {
    const first = (v: number): number => run(100, 0, { stiffness: 170, damping: 30, velocity: v }).xs.findIndex((x) => x <= 20)
    expect(first(-900)).toBeLessThan(first(0))
  })

  it('does not depend on the frame rate', () => {
    const at = (fps: number): number => { let s = { x: 100, v: 0 }; for (let i = 0; i < fps * 0.3; i += 1) s = stepSpring(s, 0, 1 / fps, { stiffness: 200, damping: 24 }); return s.x }
    expect(Math.abs(at(30) - at(60))).toBeLessThan(0.5)
    expect(Math.abs(at(60) - at(144))).toBeLessThan(0.5)
  })

  it('one very long frame cannot make it explode', () => {
    const s = stepSpring({ x: 100, v: 0 }, 0, 30, { stiffness: 200, damping: 24 })
    expect(Number.isFinite(s.x)).toBe(true)
    expect(Math.abs(s.x)).toBeLessThanOrEqual(100)
  })

  it('rubber: follows 1:1 at first, slows down, never passes its limit; the inverse gives the push back', () => {
    expect(rubber(0, 120)).toBe(0)
    expect(rubber(-5, 120)).toBe(0)
    expect(rubber(2, 120)).toBeCloseTo(2, 1)
    let last = 0
    for (let d = 10; d < 2000; d += 10) { const y = rubber(d, 120); expect(y).toBeGreaterThan(last); expect(y).toBeLessThan(120); last = y }
    for (const d of [5, 40, 140, 300]) expect(unrubber(rubber(d, 120), 120)).toBeCloseTo(d, 3)
  })
})

describe('spring() with frames', () => {
  let t = 0
  let cbs: FrameRequestCallback[] = []
  beforeEach(() => {
    t = 0; cbs = []
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback): number => { cbs.push(cb); return cbs.length })
    vi.stubGlobal('cancelAnimationFrame', () => { cbs = [] })
  })
  afterEach(() => { vi.unstubAllGlobals() })
  const frame = (): void => { const run = cbs; cbs = []; t += 16; run.forEach((cb) => cb(t)) }

  it('reports every frame, ends exactly on the target, and resolves', async () => {
    const seen: number[] = []
    const r = spring(80, 0, (x) => { seen.push(x) }, { stiffness: 200, damping: 30 })
    let done = false
    void r.done.then(() => { done = true })
    for (let i = 0; i < 400 && cbs.length; i += 1) frame()
    await Promise.resolve()
    expect(done).toBe(true)
    expect(seen[seen.length - 1]).toBe(0)
    expect(seen.length).toBeGreaterThan(10)
  })

  it('stops early when the callback says so (a page that has left the screen need not settle)', async () => {
    const seen: number[] = []
    const r = spring(0, -1000, (x) => { seen.push(x); return x <= -400 }, { stiffness: 170, damping: 30 })
    for (let i = 0; i < 400 && cbs.length; i += 1) frame()
    await r.done
    expect(seen[seen.length - 1]).toBeLessThanOrEqual(-400)
    expect(seen[seen.length - 1]).toBeGreaterThan(-1000)
  })

  it('stop() ends it where it is', async () => {
    const r = spring(0, 100, () => undefined, { stiffness: 50, damping: 10 })
    frame(); frame()
    r.stop()
    await r.done
    expect(cbs.length).toBe(0)
  })
})
