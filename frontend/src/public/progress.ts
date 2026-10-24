import { chase, type Chase } from '@/fx/math'
import { onFrame } from '@/shared/frame'

/* How much of the page has been read, 0..1, for everything that shows it (the thread menu's stitch, the back-to-top ring).
   One job in the shared frame loop reads the scroll position once per frame and lets the shown value chase it softly: a progress indicator that
   follows the raw scroll position jumps in the steps the scroll events come in (and across a whole page in one go after an anchor jump); this one glides.
   A page that does not scroll counts as 0, not 1, so a short page does not start out half-sewn. */
export interface ReadProgress {
  /** Where the scroll position really is, 0..1. */
  raw: number
  /** What to draw: chases `raw`, softly. */
  shown: number
  /** window.scrollY, for things that switch on after a certain distance. */
  scrollY: number
}
type Listener = (p: ReadProgress) => void

const listeners = new Set<Listener>()
const state: ReadProgress = { raw: 0, shown: 0, scrollY: 0 }
const c: Chase = { x: 0, v: 0 }
let stopJob: (() => void) | null = null
let fresh = true

function start(): void {
  stopJob = onFrame((_now, dt) => {
    const room = document.documentElement.scrollHeight - window.innerHeight
    const sy = window.scrollY
    const raw = room > 24 ? Math.min(1, Math.max(0, sy / room)) : 0
    if (fresh) { c.x = raw; c.v = 0; fresh = false }
    else chase(c, raw, dt)
    return () => {
      state.raw = raw
      state.shown = c.x
      state.scrollY = sy
      listeners.forEach((fn) => fn(state))
      return c.x !== raw                       // still gliding: keep the frames coming
    }
  })
}

/** Follow the progress. `fn` is called inside the write phase of a frame (so it may touch the page), now and on every frame while it changes. Returns the stop function. */
export function trackProgress(fn: Listener): () => void {
  listeners.add(fn)
  if (!stopJob) start()
  fn(state)
  return () => {
    listeners.delete(fn)
    if (!listeners.size) { stopJob?.(); stopJob = null; fresh = true }
  }
}
