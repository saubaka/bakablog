import { describe, expect, it } from 'vitest'
import { AWAY, FALLBACK_TOP, HANG_BELOW, IDLE_MS, MIN_ROOM, geometry, percent, swingTarget, tagY, wantShown } from '../src/public/hangtag'
import { isAtRest, stepSpring, type SpringState } from '../src/shared/spring'

describe('the hanging tag: where the thread is', () => {
  it('starts at the height of the menu pin and ends clear of the bottom', () => {
    const g = geometry(212, 900)
    expect(g.top).toBe(212)
    expect(g.top + g.len + HANG_BELOW).toBe(900)
  })
  it('has a fixed place when there is no menu on the left, and never a tiny thread', () => {
    expect(geometry(null, 800).top).toBe(FALLBACK_TOP)
    expect(geometry(300, 330).len).toBe(120)
  })
})

describe('the hanging tag: where it hangs', () => {
  const g = geometry(200, 900)
  it('is on the thread in proportion to what has been read', () => {
    expect(tagY(g, 0, 0)).toBe(200)
    expect(tagY(g, 1, 0)).toBe(200 + g.len)
    expect(tagY(g, 0.5, 0)).toBe(200 + g.len / 2)
  })
  it('never leaves the thread however far the spring overshoots', () => {
    expect(tagY(g, 1.2, 0)).toBe(tagY(g, 1, 0))
    expect(tagY(g, -0.3, 0)).toBe(tagY(g, 0, 0))
  })
  it('is above the screen when it is away, and bounces past its place when it drops', () => {
    expect(tagY(g, 0.4, 1)).toBeCloseTo(-AWAY, 6)
    expect(tagY(g, 0.4, -0.1)).toBeGreaterThan(tagY(g, 0.4, 0))
  })
})

describe('the hanging tag: swing, number, visibility', () => {
  it('swings against the direction of the reading speed, within limits', () => {
    expect(Math.abs(swingTarget(0))).toBe(0)
    expect(swingTarget(0.2)).toBeLessThan(0)
    expect(swingTarget(-0.2)).toBeGreaterThan(0)
    expect(swingTarget(50)).toBe(-18)
    expect(swingTarget(-50)).toBe(18)
  })
  it('shows whole percents between 0 and 100', () => {
    expect(percent(0)).toBe('0%')
    expect(percent(0.426)).toBe('43%')
    expect(percent(1.3)).toBe('100%')
    expect(percent(-1)).toBe('0%')
  })
  it('hangs out only on a page that scrolls, once the page has arrived, and on small screens only while scrolling', () => {
    const base = { armed: true, room: 3000, narrow: false, sinceScroll: 1e9 }
    expect(wantShown(base)).toBe(true)
    expect(wantShown({ ...base, armed: false })).toBe(false)
    expect(wantShown({ ...base, room: 10 })).toBe(false)
    expect(wantShown({ ...base, room: MIN_ROOM })).toBe(false)
    expect(wantShown({ ...base, narrow: true })).toBe(false)
    expect(wantShown({ ...base, narrow: true, sinceScroll: IDLE_MS - 1 })).toBe(true)
  })
})

describe('the hanging tag: the springs it is built from', () => {
  const run = (from: SpringState, to: number, o: { stiffness: number; damping: number }, seconds: number): { end: SpringState; peak: number } => {
    let s = from
    let peak = from.x
    for (let t = 0; t < seconds; t += 1 / 60) { s = stepSpring(s, to, 1 / 60, o); peak = Math.max(peak, s.x) }
    return { end: s, peak }
  }
  it('a jump of the whole page overshoots a little and then settles on the end', () => {
    const { end, peak } = run({ x: 0, v: 0 }, 1, { stiffness: 80, damping: 11 }, 4)
    expect(peak).toBeGreaterThan(1.02)
    expect(peak).toBeLessThan(1.15)
    expect(isAtRest(end, 1, 0.002)).toBe(true)
  })
  it('the drop from above bounces once and settles in its place', () => {
    const { end } = run({ x: 1, v: 0 }, 0, { stiffness: 90, damping: 9 }, 4)
    expect(Math.abs(end.x)).toBeLessThan(0.002)
  })
})
