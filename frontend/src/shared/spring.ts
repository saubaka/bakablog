/* A small spring, for motion that has to feel like something with weight: it can start from any position with any speed (a finger let go of the page
   at 900 px/s), it keeps that speed, and it settles without a fixed duration. Integrated in fixed small steps (semi-implicit Euler), so the result does not
   depend on the frame rate, and one long frame cannot make it explode. */

export interface SpringOptions {
  /** How hard it pulls towards the target (default 200). */
  stiffness?: number
  /** How much it resists moving (default 24; critical damping for stiffness k and mass 1 is 2·√k). */
  damping?: number
  mass?: number
  /** Starting speed in px (or units) per second. */
  velocity?: number
  /** It is at rest when it is this close to the target and this slow. */
  rest?: number
}

export interface SpringState { x: number; v: number }

const STEP = 1 / 240        // seconds per integration step
const MAX_FRAME = 1 / 20    // a frame longer than this (tab in the background, long task) counts as this long

/** Advance a spring by `dt` seconds. Pure: the same inputs always give the same state (the tests drive it directly). */
export function stepSpring(s: SpringState, to: number, dt: number, o: SpringOptions = {}): SpringState {
  const k = o.stiffness ?? 200
  const c = o.damping ?? 24
  const m = o.mass ?? 1
  let { x, v } = s
  let left = Math.min(dt, MAX_FRAME)
  while (left > 1e-9) {
    const h = Math.min(STEP, left)
    v += ((-k * (x - to) - c * v) / m) * h
    x += v * h
    left -= h
  }
  return { x, v }
}

export const isAtRest = (s: SpringState, to: number, rest = 0.4): boolean => Math.abs(s.x - to) < rest && Math.abs(s.v) < rest * 8

export interface SpringRun {
  /** Resolves when the spring has settled on the target (or `until` said stop). */
  done: Promise<void>
  /** Stop where it is; `done` resolves. */
  stop: () => void
}

/** Animate `from` → `to`. `onUpdate(x, v)` is called every frame; returning `true` from it ends the run early (a page that has left the screen need not settle). */
export function spring(from: number, to: number, onUpdate: (x: number, v: number) => boolean | void, o: SpringOptions = {}): SpringRun {
  let s: SpringState = { x: from, v: o.velocity ?? 0 }
  let raf = 0
  let last = 0
  let finish: () => void = () => undefined
  const done = new Promise<void>((resolve) => { finish = resolve })
  const stop = (): void => { cancelAnimationFrame(raf); finish() }
  const frame = (now: number): void => {
    const dt = last ? (now - last) / 1000 : 1 / 60
    last = now
    s = stepSpring(s, to, dt, o)
    const rest = isAtRest(s, to, o.rest)
    if (rest) s = { x: to, v: 0 }
    if (onUpdate(s.x, s.v) === true || rest) { finish(); return }
    raf = requestAnimationFrame(frame)
  }
  raf = requestAnimationFrame(frame)
  return { done, stop }
}

/** Resistance past the edge: follows the finger 1:1 at first, then slows down and never goes past `limit` (the way a stretched rubber band does). */
export function rubber(distance: number, limit: number): number {
  if (distance <= 0) return 0
  return limit * (1 - Math.exp(-distance / limit))
}

/** The push that produces a given displacement: lets a push pick up exactly where a spring-back was when the finger comes back down. */
export function unrubber(offset: number, limit: number): number {
  const o = Math.min(Math.max(offset, 0), limit * 0.999)
  return -limit * Math.log(1 - o / limit)
}
