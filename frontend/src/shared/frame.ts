/* One frame loop for everything that follows the scroll position.
   Several parts of the page react to scrolling (the motion engine, the thread menu's progress, the back-to-top ring, the reading line, the table of
   contents). If each had its own `requestAnimationFrame`, one frame would read the layout, write styles, read again (making the browser recalculate
   styles in the middle of the frame), write again ... Here every job first READS (scroll position, sizes, rectangles) and hands back a function that WRITES;
   the loop runs all the reads, then all the writes. One style recalculation per frame, whoever is listening.

   A job runs on every frame while the page is being scrolled and for a moment after, and as long as one of its writes returns `true` ("I am still moving"). */

export type Write = () => boolean | void
export type Job = (now: number, dt: number) => Write | void

const SETTLE_MS = 160        // keep going this long after the last scroll / resize
const MAX_DT = 50            // a frame longer than this (a hidden tab, a long task) counts as this long

const jobs = new Set<Job>()
let raf = 0
let started = false
let lastEvent = -1e9
let prev = 0

function run(now: number): void {
  raf = 0
  const dt = prev > 0 ? Math.min(Math.max(now - prev, 0), MAX_DT) : 1000 / 60   // the first frame after an idle spell counts as one ordinary frame
  prev = now
  const writes: Write[] = []
  for (const job of jobs) { const w = job(now, dt); if (w) writes.push(w) }
  let keep = performance.now() - lastEvent < SETTLE_MS
  for (const w of writes) if (w() === true) keep = true
  if (keep && jobs.size) raf = requestAnimationFrame(run)
  else prev = 0
}

/** Ask for a frame (something changed that a job needs to look at). Cheap to call many times. */
export function wake(): void {
  lastEvent = performance.now()
  if (!raf && jobs.size) raf = requestAnimationFrame(run)
}

function listen(): void {
  if (started || typeof window === 'undefined') return
  started = true
  window.addEventListener('scroll', wake, { passive: true })
  window.addEventListener('resize', wake, { passive: true })
}

/** Join the loop. The returned function leaves it. */
export function onFrame(job: Job): () => void {
  listen()
  jobs.add(job)
  wake()
  return () => { jobs.delete(job) }
}

/** For tests: forget every job and stop. */
export function __resetFrames(): void {
  jobs.clear()
  if (raf) cancelAnimationFrame(raf)
  raf = 0
  prev = 0
}
