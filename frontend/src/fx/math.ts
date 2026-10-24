/* The numbers behind the scroll motion. The TARGET for any scroll offset is a pure function of the scroll position and the
   element's box, so wherever the page ends up (anchor jump, back/forward, fling) the picture it settles on is the same.
   What is SHOWN chases that target like something with a little weight (see chase): it starts and stops softly, never moves faster than
   one full change per MIN_MS, so a big or fast scroll never makes anything pop in or vanish, and a slow scroll is followed closely. */

export const ENTER_START = 0.94   // top edge crosses 94% of the viewport height -> starts
export const ENTER_SPAN = 0.3     // ... and is complete 30% of the viewport later
export const EXIT_SPAN = 0.16     // bottom edge inside the top 16% -> leaving
export const STAGGER = 0.08       // delay between neighbours in one row
export const TALL = 0.9           // taller than 90% of the viewport: fade in only, never fade out
export const SPREAD = 0.6         // share of a heading's progress spent staggering its characters
export const MAX_STAGGER = 5      // columns beyond the sixth start together with the sixth
export const MIN_MS = 420         // the shortest time a complete change (0 -> 1 or 1 -> 0) may take, however far or fast the page scrolled
export const SMOOTH = 0.05        // seconds: how softly the shown value starts and stops (also how far it trails a steadily moving target: about speed x SMOOTH)
export const MAX_SPEED = 1000 / MIN_MS   // units per second: one complete change per MIN_MS
export const MAX_DT = 50          // longest gap between two frames that counts as elapsed time (a hidden tab or a long task must not use it all in one step)

export type FxState = 'pre' | 'active' | 'done' | 'post'

export const clamp = (v: number, a = 0, b = 1): number => (v < a ? a : v > b ? b : v)
export const ease = (t: number): number => 1 - (1 - t) ** 3
export const round3 = (v: number): number => Math.round(v * 1000) / 1000

/** Entering, 0..1 (not eased). `top` is the element's top edge relative to the viewport top. */
export function enter(top: number, vh: number, stagI = 0, stagN = 1): number {
  let t = clamp((vh * ENTER_START - top) / (vh * ENTER_SPAN))
  if (stagN > 1) t = clamp((t - STAGGER * stagI) / (1 - STAGGER * (stagN - 1)))
  return t
}

/** Leaving, 0..1 (not eased). Elements taller than 90% of the viewport never leave, so a long figure does not blink while it is read. */
export function exit(bottom: number, vh: number, tall: boolean): number {
  return tall ? 0 : clamp((vh * EXIT_SPAN - bottom) / (vh * EXIT_SPAN))
}

/** Parallax offset in -1..1: 0 when the element's centre is at the middle of the viewport. */
export function drift(top: number, h: number, sy: number, vh: number): number {
  return round3(clamp(((top - sy + h / 2) - vh / 2) / vh, -1, 1))
}

/** How much of a long line (timeline spine) has been read, 0..1: it grows while its section scrolls past 70% of the viewport. */
export function spine(top: number, h: number, sy: number, vh: number): number {
  return round3(clamp((sy + vh * 0.7 - top) / Math.max(h, 1)))
}

export function stateOf(a: number, b: number): FxState {
  return b >= 1 ? 'post' : a >= 1 && b <= 0 ? 'done' : a <= 0 && b <= 0 ? 'pre' : 'active'
}

/** Where the scroll position says the element should be: entering and leaving, 0..1, not eased. */
export function target(top: number, h: number, vh: number, tall: boolean, stagI = 0, stagN = 1, intro = 1): { tin: number; tout: number } {
  return { tin: Math.min(enter(top, vh, stagI, stagN), clamp(intro)), tout: exit(top + h, vh, tall) }
}

export interface Chase { x: number; v: number }

/** One step of the shown value `s` (position x, speed v in units per second) towards its target `goal`, `dtMs` milliseconds later.
    A critically damped follower with a speed limit (the classic "smooth damp"): it speeds up and slows down smoothly instead of switching between
    "exactly there" and "full speed", it never goes faster than MAX_SPEED (so a complete change takes at least MIN_MS), it never overshoots,
    it turns around smoothly when the target does, and it lands exactly. Changes `s` in place. */
export function chase(s: Chase, goal: number, dtMs: number): void {
  let left = clamp(dtMs, 0, MAX_DT) / 1000
  while (left > 1e-9) {                         // fixed small steps: the result hardly depends on the frame rate
    const h = Math.min(left, 1 / 120)
    chaseStep(s, goal, h)
    left -= h
  }
  if (Math.abs(s.x - goal) < 0.0004 && Math.abs(s.v) < 0.01) { s.x = goal; s.v = 0 }
}

function chaseStep(s: Chase, goal: number, dt: number): void {
  const omega = 2 / SMOOTH
  const k = omega * dt
  const damp = 1 / (1 + k + 0.48 * k * k + 0.235 * k * k * k)
  const maxChange = MAX_SPEED * SMOOTH
  const change = clamp(s.x - goal, -maxChange, maxChange)
  const reach = s.x - change
  const temp = (s.v + omega * change) * dt
  s.v = (s.v - omega * temp) * damp
  let out = reach + (change + temp) * damp
  if ((goal - s.x > 0) === (out > goal)) { out = goal; s.v = 0 }     // it would pass the target: stop on it
  s.x = out
}

/** The two numbers written to --fx-in / --fx-out (eased, rounded to three decimals so unchanged values are not rewritten). */
export function shape(tin: number, tout: number): { in: number; out: number; state: FxState } {
  const a = round3(ease(tin))
  const b = round3(ease(tout))
  return { in: a, out: b, state: stateOf(a, b) }
}

/** Target and shape in one go: what the picture is once the motion has caught up with the scroll position. */
export function progress(top: number, h: number, vh: number, tall: boolean, stagI = 0, stagN = 1, intro = 1): { in: number; out: number; state: FxState } {
  const t = target(top, h, vh, tall, stagI, stagN, intro)
  return shape(t.tin, t.tout)
}

/** Per-character offset of a heading: characters start one after another over the first SPREAD of the heading's own progress. */
export function charOffset(index: number, count: number): number {
  return count > 1 ? Number(((index / (count - 1)) * SPREAD).toFixed(3)) : 0
}
