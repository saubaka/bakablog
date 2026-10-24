import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { __resetFrames, onFrame, wake } from '@/shared/frame'

let t = 0
let cbs: FrameRequestCallback[] = []
const frame = (n = 1): void => { for (let i = 0; i < n; i += 1) { const run = cbs; cbs = []; t += 16; run.forEach((cb) => cb(t)) } }

beforeEach(() => {
  t = 0; cbs = []
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback): number => { cbs.push(cb); return cbs.length })
  vi.stubGlobal('cancelAnimationFrame', () => { cbs = [] })
})
afterEach(() => { __resetFrames(); vi.unstubAllGlobals() })

describe('the shared frame loop', () => {
  it('every job reads before any job writes, however many there are and in whatever order they joined', () => {
    const log: string[] = []
    const stopA = onFrame(() => { log.push('read A'); return () => { log.push('write A') } })
    const stopB = onFrame(() => { log.push('read B'); return () => { log.push('write B') } })
    const stopC = onFrame(() => { log.push('read C') })                    // a job with nothing to write
    frame()
    expect(log).toEqual(['read A', 'read B', 'read C', 'write A', 'write B'])
    ;[stopA, stopB, stopC].forEach((stop) => stop())
  })

  it('one frame request serves all of them', () => {
    const stops = [onFrame(() => undefined), onFrame(() => undefined), onFrame(() => undefined)]
    expect(cbs.length).toBe(1)
    wake(); wake()
    expect(cbs.length).toBe(1)
    stops.forEach((stop) => stop())
  })

  it('keeps going while a write says it is still moving, and the first frame after a rest counts as one ordinary frame', () => {
    let moving = 5
    const dts: number[] = []
    const stop = onFrame((_now, dt) => { dts.push(dt); return () => { moving -= 1; return moving > 0 } })
    frame(10)
    expect(dts.length).toBeGreaterThanOrEqual(5)
    expect(dts[0]).toBeCloseTo(1000 / 60, 3)
    expect(dts.slice(1).every((d) => Math.abs(d - 16) < 0.001)).toBe(true)
    stop()
  })

  it('a job that has left is not called again', () => {
    let calls = 0
    const stop = onFrame(() => { calls += 1 })
    frame()
    stop()
    wake()
    frame(3)
    expect(calls).toBe(1)
  })

  it('a very long gap between frames counts as at most 50 ms', () => {
    const dts: number[] = []
    const stop = onFrame((_now, dt) => { dts.push(dt); return () => true })
    frame(2)
    t += 10_000
    frame()
    expect(Math.max(...dts)).toBeLessThanOrEqual(50)
    stop()
  })
})
