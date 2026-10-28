/* The motion of the menu thread, as numbers (the drawing is in layout/ThreadNav.vue).
   Positions are in "bead units": bead k is at k, the knot at the end of the thread is at n (n - 0.5 on the bottom bar, where the last cell is only half a cell wide).

   - The heart is a spring that is aimed at a bead. It is aimed the moment a page change is decided (a click on a bead, a push past the edge of the page that went far
     enough), not when the new page has finally arrived, so the menu answers at once and keeps moving while the page is still being fetched. Aimed somewhere else
     in mid-flight it keeps its speed. A push that has not gone far enough only leans it towards the bead.
   - The pink thread is not a progress value that happens to sit under the current bead: it is a thread tied to the bead the heart came from (the anchor, a slower spring)
     and pulled along by the heart. When the heart arrives the anchor catches up and the thread is reeled in, so the line goes down to the new bead and stops there.
     What has been read of the page is added at the end of it (from the bead that is current, towards the next one).
   - The heart stretches a little along its way while it is fast. */
import { stepSpring, type SpringState } from '@/shared/spring'

export const HEART = { stiffness: 170, damping: 15 }       // a little bounce: about 10 % overshoot, settles in about half a second
export const ANCHOR = { stiffness: 60, damping: 14 }       // follows the heart more slowly, without bounce: the pink thread trails behind it and is reeled in
export const ENDS = { stiffness: 300, damping: 34 }        // the two ends of the pink thread glide to where they should be (about a tenth of a second, no bounce): nothing in it ever jumps

export interface Motion {
  heart: SpringState
  anchor: SpringState
  /** The bead the heart is heading for. */
  to: number
  /** The stretch of thread the heart is travelling over: the pink part never runs past it (no thread beyond the bead it travelled to). */
  lo: number
  hi: number
  /** Where the two ends of the pink thread are drawn (they glide to the ends `pink` asks for). */
  ends: { from: SpringState; to: SpringState }
}

export const makeMotion = (at: number): Motion => ({ heart: { x: at, v: 0 }, anchor: { x: at, v: 0 }, to: at, lo: at, hi: at, ends: { from: { x: at, v: 0 }, to: { x: at, v: 0 } } })

/** Head for another bead (the speed is kept). */
export function aim(m: Motion, to: number): void {
  if (to === m.to) return
  m.lo = Math.min(m.anchor.x, to)
  m.hi = Math.max(m.anchor.x, to)
  m.to = to
}

/** Jump to a bead without travelling (first paint, the page that is shown is not in the menu any more / again, reduced motion). */
export function place(m: Motion, at: number): void {
  m.heart = { x: at, v: 0 }
  m.anchor = { x: at, v: 0 }
  m.to = m.lo = m.hi = at
  m.ends = { from: { x: at, v: 0 }, to: { x: at, v: 0 } }
}

/** One step of `dt` seconds. `lean` is how far past the bead the heart is pulled by a push that has not gone far enough to turn the page (bead units, signed). */
export function step(m: Motion, lean: number, dt: number): void {
  m.heart = stepSpring(m.heart, m.to + lean, dt, HEART)
  m.anchor = stepSpring(m.anchor, m.to, dt, ANCHOR)
}

export const atRest = (m: Motion, lean: number): boolean =>
  Math.abs(m.heart.x - (m.to + lean)) < 0.0015 && Math.abs(m.heart.v) < 0.01 && Math.abs(m.anchor.x - m.to) < 0.0015 && Math.abs(m.anchor.v) < 0.01

const clamp = (x: number, lo: number, hi: number): number => Math.min(Math.max(x, lo), hi)

export interface Pink { from: number; to: number }

/** The pink thread: from where it is tied to where the heart or the reading has taken it. `current` is the bead of the page that is shown, `read` how much of that page has been
    read (0..1) and `reach` how far that gets towards the next bead (1; a half on the bottom bar for the last bead, whose "next" is the end of the bar). */
export function pink(m: Motion, current: number, read: number, reach: number): Pink {
  const travelling = m.lo !== m.hi
  const heart = travelling ? clamp(m.heart.x, m.lo, m.hi) : m.heart.x      // no thread beyond the bead it travelled to, however far the springs overshoot
  const anchor = travelling ? clamp(m.anchor.x, m.lo, m.hi) : m.anchor.x
  // what has been read of the page only counts while the visitor stays on it or goes forward: heading for an entry ABOVE it the thread is only the one the heart pulls, which is
  // reeled in with the anchor (a read part pinned to the bead being left would hold the thread's end there until the page changed, and then drop it in one frame)
  const readTip = m.to < current ? -Infinity : current + clamp(read, 0, 1) * reach
  return { from: Math.min(anchor, heart), to: Math.max(anchor, heart, readTip) }
}

/** What is drawn: the ends of the thread glide to the ends `pink` asks for, so a change of what is asked (the page has changed, the reading jumped, the heart left) is a quick glide and
    never a jump. Returns the drawn thread. */
export function settle(m: Motion, want: Pink, dt: number): Pink {
  m.ends.from = stepSpring(m.ends.from, want.from, dt, ENDS)
  m.ends.to = stepSpring(m.ends.to, want.to, dt, ENDS)
  return { from: Math.min(m.ends.from.x, m.ends.to.x), to: Math.max(m.ends.from.x, m.ends.to.x) }
}

/** Jump the drawn thread to where it should be (first paint, reduced motion). */
export function placeEnds(m: Motion, want: Pink): Pink {
  m.ends = { from: { x: want.from, v: 0 }, to: { x: want.to, v: 0 } }
  return want
}

export const endsAtRest = (m: Motion, want: Pink): boolean =>
  Math.abs(m.ends.from.x - want.from) < 0.0015 && Math.abs(m.ends.to.x - want.to) < 0.0015 && Math.abs(m.ends.from.v) < 0.01 && Math.abs(m.ends.to.v) < 0.01

/** How much the heart is stretched along its way (1 = round), for a speed in beads per second. */
export const stretch = (speed: number): number => 1 + Math.min(Math.abs(speed) * 0.07, 0.22)
