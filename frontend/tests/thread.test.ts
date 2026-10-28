import { describe, expect, it } from 'vitest'
import { aim, atRest, endsAtRest, makeMotion, pink, place, placeEnds, settle, step, stretch, type Motion } from '../src/public/thread'
import { prefetchOrder } from '../src/public/prefetch'

const run = (m: Motion, lean: number, seconds: number, each?: (m: Motion) => void): void => {
  for (let t = 0; t < seconds; t += 1 / 60) { step(m, lean, 1 / 60); each?.(m) }
}

describe('the menu thread: the heart', () => {
  it('rests on its bead and stays there', () => {
    const m = makeMotion(2)
    run(m, 0, 1)
    expect(m.heart.x).toBe(2)
    expect(atRest(m, 0)).toBe(true)
  })
  it('travels to a new bead with a little bounce and settles on it', () => {
    const m = makeMotion(1)
    aim(m, 2)
    let peak = 1
    run(m, 0, 3, (s) => { peak = Math.max(peak, s.heart.x) })
    expect(peak).toBeGreaterThan(2.02)
    expect(peak).toBeLessThan(2.25)
    expect(Math.abs(m.heart.x - 2)).toBeLessThan(0.002)
    expect(atRest(m, 0)).toBe(true)
  })
  it('is on its way within the first frames: it does not wait for anything', () => {
    const m = makeMotion(1)
    aim(m, 2)
    run(m, 0, 4 / 60)
    expect(m.heart.x).toBeGreaterThan(1.02)
  })
  it('keeps its speed when it is aimed somewhere else in mid-flight', () => {
    const m = makeMotion(0)
    aim(m, 3)
    run(m, 0, 0.25)
    const { x, v } = m.heart
    expect(v).toBeGreaterThan(1)
    aim(m, 1)
    step(m, 0, 1 / 240)
    expect(Math.abs(m.heart.x - x)).toBeLessThan(0.02)       // no jump
    expect(Math.abs(m.heart.v - v)).toBeLessThan(2)          // the speed changes by the pull of the new bead, it is not reset
    run(m, 0, 3)
    expect(Math.abs(m.heart.x - 1)).toBeLessThan(0.002)       // and it ends on the bead it was last aimed at
  })
  it('is pulled by a push that has not gone far enough, and goes back', () => {
    const m = makeMotion(1)
    run(m, 0.4, 2)
    expect(m.heart.x).toBeCloseTo(1.4, 2)
    run(m, 0, 3)
    expect(m.heart.x).toBeCloseTo(1, 2)
  })
  it('can be placed without travelling', () => {
    const m = makeMotion(1)
    aim(m, 2)
    run(m, 0, 0.1)
    place(m, 3)
    expect(m.heart.x).toBe(3)
    expect(m.heart.v).toBe(0)
    expect(atRest(m, 0)).toBe(true)
  })
  it('stretches along its way while it is fast and is round at rest', () => {
    expect(stretch(0)).toBe(1)
    expect(stretch(3)).toBeGreaterThan(1.15)
    expect(stretch(-3)).toBe(stretch(3))
    expect(stretch(100)).toBeLessThanOrEqual(1.22)
  })
})

describe('the menu thread: the pink thread', () => {
  it('is nothing on a page that has not been read', () => {
    const m = makeMotion(2)
    expect(pink(m, 2, 0, 1)).toEqual({ from: 2, to: 2 })
  })
  it('grows from the current bead towards the next as the page is read (a half cell to the end of the bar for the last)', () => {
    const m = makeMotion(2)
    expect(pink(m, 2, 0.5, 1)).toEqual({ from: 2, to: 2.5 })
    expect(pink(m, 2, 1, 0.5)).toEqual({ from: 2, to: 2.5 })
  })
  it('goes down to the new bead and stops there: never a thread below the bead that was travelled to, however the page was read or the spring bounced', () => {
    const m = makeMotion(1)
    aim(m, 2)                                                // the page was read to its end: the thread was full, from 1 to 2
    let lowest = 0
    let seen = 0
    for (let t = 0; t < 3; t += 1 / 60) {
      step(m, 0, 1 / 60)
      const afterTheChange = t > 0.1                         // the route has changed: bead 2 is current and the new page is at its start
      const pk = pink(m, afterTheChange ? 2 : 1, afterTheChange ? 0 : 1, 1)
      lowest = Math.max(lowest, pk.to)
      if (afterTheChange && pk.to - pk.from > 0.001) seen += 1
    }
    expect(lowest).toBeLessThanOrEqual(2)
    expect(seen).toBeGreaterThan(5)                          // it is there, being reeled in, not cut off
    const end = pink(m, 2, 0, 1)
    expect(end.to - end.from).toBeLessThan(0.002)            // and nothing is left of it when the heart is home
  })
  it('trails behind the heart going up as well, and is reeled in at the bead above', () => {
    const m = makeMotion(3)
    aim(m, 2)
    let longest = 0
    for (let t = 0; t < 3; t += 1 / 60) {
      step(m, 0, 1 / 60)
      const pk = pink(m, t > 0.1 ? 2 : 3, 0, 1)
      longest = Math.max(longest, pk.to - pk.from)
      expect(pk.from).toBeGreaterThanOrEqual(2 - 1e-9)
      expect(pk.to).toBeLessThanOrEqual(3 + 1e-9)
    }
    expect(longest).toBeGreaterThan(0.3)
    const end = pink(m, 2, 0, 1)
    expect(end.to - end.from).toBeLessThan(0.002)
  })
})

describe('the menu thread: nothing in it ever jumps', () => {
  /** Runs a page change frame by frame the way ThreadNav does and returns the drawn thread's length in every frame. `routeAt`: when the route (and with it the page that is shown) changes. */
  const lengths = (from: number, to: number, readBefore: number, routeAt: number, seconds = 2.5): number[] => {
    const m = makeMotion(from)
    placeEnds(m, pink(m, from, readBefore, 1))
    const out: number[] = [m.ends.to.x - m.ends.from.x]
    aim(m, to)
    for (let t = 0; t < seconds; t += 1 / 60) {
      step(m, 0, 1 / 60)
      const after = t >= routeAt
      const drawn = settle(m, pink(m, after ? to : from, after ? 0 : readBefore, 1), 1 / 60)
      out.push(drawn.to - drawn.from)
    }
    return out
  }
  const biggestStep = (xs: number[]): number => xs.reduce((m, x, i) => (i ? Math.max(m, Math.abs(x - xs[i - 1]!)) : m), 0)

  it('heading up (the push past the top): the thread is reeled in smoothly, also in the frame where the page changes', () => {
    const xs = lengths(2, 1, 0, 0.35)
    expect(biggestStep(xs)).toBeLessThan(0.1)                  // a tenth of a bead is nine pixels: the thread used to lose a whole bead in one frame here
    expect(xs[xs.length - 1]).toBeLessThan(0.002)
  })
  it('heading up from the middle of a page: what had been read glides away instead of being cut off', () => {
    const xs = lengths(3, 2, 0.6, 0.3)
    expect(biggestStep(xs)).toBeLessThan(0.1)
    expect(xs[xs.length - 1]).toBeLessThan(0.002)
  })
  it('heading down from a page that was read to the end or only half: smooth in the frame where the page changes', () => {
    for (const read of [1, 0.5, 0.1]) {
      const xs = lengths(1, 2, read, 0.06)                     // a click on a bead with the data already in: the page changes almost at once
      expect(biggestStep(xs)).toBeLessThan(0.1)
      expect(xs[xs.length - 1]).toBeLessThan(0.002)
    }
  })
  it('never runs past the bead it went to', () => {
    const m = makeMotion(1)
    placeEnds(m, pink(m, 1, 0.5, 1))
    aim(m, 2)
    let furthest = 0
    for (let t = 0; t < 3; t += 1 / 60) {
      step(m, 0, 1 / 60)
      const drawn = settle(m, pink(m, t > 0.06 ? 2 : 1, t > 0.06 ? 0 : 0.5, 1), 1 / 60)
      furthest = Math.max(furthest, drawn.to)
    }
    expect(furthest).toBeLessThanOrEqual(2.001)
  })
  it('is at rest when the ends have arrived', () => {
    const m = makeMotion(2)
    const want = pink(m, 2, 0.4, 1)
    expect(endsAtRest(m, want)).toBe(false)
    for (let t = 0; t < 2; t += 1 / 60) settle(m, want, 1 / 60)
    expect(endsAtRest(m, want)).toBe(true)
  })
})

describe('getting the neighbouring pages ready', () => {
  const urls = ['/', '/blog', '/moments', '/archive']
  it('asks for the next entry first, then the previous one, then the rest by distance', () => {
    expect(prefetchOrder(urls, 1)).toEqual(['/moments', '/', '/archive'])
    expect(prefetchOrder(urls, 0)).toEqual(['/blog', '/moments', '/archive'])
    expect(prefetchOrder(urls, 3)).toEqual(['/moments', '/blog', '/'])
  })
  it('asks for every entry when the page shown is not in the menu', () => {
    expect(prefetchOrder(urls, -1)).toEqual(urls)
  })
})
