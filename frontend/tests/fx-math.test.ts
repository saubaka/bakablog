import { describe, expect, it } from 'vitest'
import { charOffset, chase, clamp, drift, ease, enter, exit, MAX_DT, MAX_SPEED, MIN_MS, progress, shape, SMOOTH, spine, stateOf, SPREAD, target, type Chase } from '@/fx/math'

describe('scroll motion math', () => {
  const vh = 1000

  const run = (from: number, goals: (t: number) => number, ms: number, dt = 1000 / 60): { xs: number[]; vs: number[]; end: Chase } => {
    const c: Chase = { x: from, v: 0 }
    const xs: number[] = []; const vs: number[] = []
    for (let t = 0; t < ms; t += dt) { chase(c, goals(t), dt); xs.push(c.x); vs.push(c.v) }
    return { xs, vs, end: c }
  }

  it('chase: a complete change takes at least MIN_MS, never goes faster than MAX_SPEED, and lands exactly', () => {
    const { xs, vs, end } = run(0, () => 1, 2000)
    expect(end.x).toBe(1)
    expect(Math.max(...vs)).toBeLessThanOrEqual(MAX_SPEED * 1.001)
    const arrived = xs.findIndex((x) => x >= 1) * (1000 / 60)
    expect(arrived).toBeGreaterThanOrEqual(MIN_MS - 17)
    expect(arrived).toBeLessThanOrEqual(MIN_MS + 400)      // soft start and stop add a little, not a lot
    const back = run(1, () => 0, 2000)
    expect(back.end.x).toBe(0)
    expect(Math.min(...back.vs)).toBeGreaterThanOrEqual(-MAX_SPEED * 1.001)
  })

  it('chase: starts and stops softly: the speed changes gradually, not from nothing to full speed in one frame', () => {
    const { vs } = run(0, () => 1, 1500)
    expect(vs[0]).toBeLessThan(MAX_SPEED * 0.8)             // the first frame is not yet at full speed
    let worst = 0
    for (let i = 1; i < vs.length; i += 1) worst = Math.max(worst, Math.abs((vs[i] as number) - (vs[i - 1] as number)))
    expect(worst).toBeLessThan(MAX_SPEED * 0.8)             // no frame changes the speed by more than 80% of the top speed (it takes about three frames to get there)
  })

  it('chase: never overshoots, and turns around smoothly when the target does', () => {
    const up = run(0, () => 1, 1500)
    expect(Math.max(...up.xs)).toBeLessThanOrEqual(1)
    const turn = run(0, (t) => (t < 220 ? 1 : 0), 1500)
    expect(Math.max(...turn.xs)).toBeLessThan(0.6)           // it had only got part of the way
    expect(Math.min(...turn.xs)).toBeGreaterThanOrEqual(0)
    expect(turn.end.x).toBe(0)
    for (let i = 1; i < turn.xs.length; i += 1) expect(Math.abs((turn.xs[i] as number) - (turn.xs[i - 1] as number))).toBeLessThan(MAX_SPEED / 60 * 1.05)
  })

  it('chase: a target that moves slowly is followed closely: it trails by about speed x SMOOTH and no more', () => {
    const speed = 0.8                                          // units per second, well under the limit
    const { xs } = run(0, (t) => (t / 1000) * speed, 1500)
    const lag = (1500 / 1000) * speed - (xs[xs.length - 1] as number)
    expect(lag).toBeGreaterThan(0)
    expect(lag).toBeLessThan(speed * SMOOTH * 1.3)
  })

  it('chase: does not depend much on the frame rate, and one very long frame cannot make it jump', () => {
    const at = (fps: number): number => { const c: Chase = { x: 0, v: 0 }; for (let i = 0; i < fps * 0.3; i += 1) chase(c, 1, 1000 / fps); return c.x }
    expect(Math.abs(at(30) - at(60))).toBeLessThan(0.04)
    expect(Math.abs(at(60) - at(144))).toBeLessThan(0.04)
    const c: Chase = { x: 0, v: 0 }
    chase(c, 1, 10_000)                                        // a hidden tab coming back: counts as MAX_DT
    expect(c.x).toBeLessThanOrEqual(MAX_SPEED * (MAX_DT / 1000) * 1.001)
  })

  it('target and shape together are progress', () => {
    for (const top of [1200, 940, 790, 640, 100, -300]) for (const h of [80, 400, 950]) {
      const t = target(top, h, vh, h > vh * 0.9, 1, 3)
      expect(shape(t.tin, t.tout)).toEqual(progress(top, h, vh, h > vh * 0.9, 1, 3))
    }
    expect(shape(1, 0).state).toBe('done')
    expect(shape(0, 0).state).toBe('pre')
    expect(shape(1, 1).state).toBe('post')
    expect(shape(0.4, 0).state).toBe('active')
  })

  it('clamp and ease', () => {
    expect(clamp(-1)).toBe(0)
    expect(clamp(2)).toBe(1)
    expect(clamp(0.4)).toBe(0.4)
    expect(ease(0)).toBe(0)
    expect(ease(1)).toBe(1)
    expect(ease(0.5)).toBeCloseTo(0.875, 5)
  })

  it('enters while the top edge travels from 94% to 64% of the viewport', () => {
    expect(enter(940, vh)).toBe(0)
    expect(enter(1200, vh)).toBe(0)
    expect(enter(790, vh)).toBeCloseTo(0.5, 5)
    expect(enter(640, vh)).toBe(1)
    expect(enter(100, vh)).toBe(1)
  })

  it('leaves while the bottom edge is inside the top 16%; tall elements never leave', () => {
    expect(exit(160, vh, false)).toBe(0)
    expect(exit(80, vh, false)).toBeCloseTo(0.5, 5)
    expect(exit(0, vh, false)).toBe(1)
    expect(exit(-300, vh, false)).toBe(1)
    expect(exit(0, vh, true)).toBe(0)
  })

  it('staggers neighbours in a row without ever exceeding the range', () => {
    // three in a row: the third starts later and ends at 1 together with the others
    const t = (i: number) => enter(700, vh, i, 3)
    expect(t(0)).toBeGreaterThan(t(1))
    expect(t(1)).toBeGreaterThan(t(2))
    for (const top of [-500, 100, 640, 700, 900, 1500]) for (let i = 0; i < 3; i += 1) {
      const v = enter(top, vh, i, 3)
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThanOrEqual(1)
    }
    expect(enter(640, vh, 2, 3)).toBe(1)
  })

  it('progress is a pure function of position: same input, same output, and monotonic in scroll', () => {
    expect(progress(500, 200, vh, false)).toEqual(progress(500, 200, vh, false))
    let lastIn = -1
    for (let top = 1100; top >= 300; top -= 20) {        // scrolling down: the element moves up
      const p = progress(top, 200, vh, false)
      expect(p.in).toBeGreaterThanOrEqual(lastIn)
      lastIn = p.in
    }
    let lastOut = -1
    for (let top = 300; top >= -400; top -= 20) {
      const p = progress(top, 200, vh, false)
      expect(p.out).toBeGreaterThanOrEqual(lastOut)
      lastOut = p.out
    }
  })

  it('an element in the middle of the screen has no transform at all (state done)', () => {
    const p = progress(400, 200, vh, false)
    expect(p).toEqual({ in: 1, out: 0, state: 'done' })
  })

  it('the intro clock caps the entrance', () => {
    expect(progress(300, 100, vh, false, 0, 1, 0).in).toBe(0)
    expect(progress(300, 100, vh, false, 0, 1, 0.5).in).toBeCloseTo(0.875, 5)
    expect(progress(300, 100, vh, false, 0, 1, 1).in).toBe(1)
  })

  it('state names', () => {
    expect(stateOf(0, 0)).toBe('pre')
    expect(stateOf(0.4, 0)).toBe('active')
    expect(stateOf(1, 0)).toBe('done')
    expect(stateOf(1, 0.2)).toBe('active')
    expect(stateOf(1, 1)).toBe('post')
  })

  it('drift and spine stay within their ranges', () => {
    expect(drift(0, 100, 0, vh)).toBeGreaterThanOrEqual(-1)
    expect(drift(5000, 100, 0, vh)).toBe(1)
    expect(drift(-5000, 100, 0, vh)).toBe(-1)
    expect(drift(450, 100, 0, vh)).toBe(0)
    expect(spine(1000, 400, 0, vh)).toBe(0)
    expect(spine(0, 400, 0, vh)).toBe(1)
    expect(spine(500, 1000, 0, vh)).toBeCloseTo(0.2, 3)
  })

  it('characters start one after another over the first 60% of the heading progress', () => {
    expect(charOffset(0, 10)).toBe(0)
    expect(charOffset(9, 10)).toBe(SPREAD)
    expect(charOffset(0, 1)).toBe(0)
    const offs = Array.from({ length: 10 }, (_, i) => charOffset(i, 10))
    expect([...offs].sort((a, b) => a - b)).toEqual(offs)
  })
})
