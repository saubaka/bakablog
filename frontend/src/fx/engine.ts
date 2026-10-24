/* Scroll motion engine.

   Every [data-fx] element has two progress numbers (see ./math.ts). Their TARGETS are a pure function of the scroll position:
     in  (0..1)  the element's top edge travels from 94% to 64% of the viewport height  -> entering
     out (0..1)  the element's bottom edge travels from 16% of the viewport height to 0 -> leaving
   What is SHOWN follows the target at a limited speed: a complete change (0 -> 1 or 1 -> 0) takes at least MIN_MS, however
   far or fast the page scrolled. Scrolling slowly is followed exactly (shown === target); a fling, an anchor jump or a
   back/forward restore makes the elements glide for MIN_MS instead of popping in or vanishing.
   The shown numbers are written as --fx-in / --fx-out and data-fx-state (pre | active | done | post); ui/css/fx.css turns
   them into opacity / translate / scale / rotate / clip-path. Nothing is triggered once, so nothing can get stuck: the
   shown value always keeps moving towards the target of the current position and arrives there. Two exceptions are placed
   at once: an element's very first picture (a page that just opened must not animate from nothing) and a focused element
   (it must never be transparent).

   Cost control: positions are measured once per layout change (offsetTop chain, which ignores our own transforms, so
   there is no feedback loop); each frame is arithmetic on cached numbers, values are only written when they change.
   The frame itself belongs to the shared loop (shared/frame.ts): this module READS and computes in the loop's first phase and hands back a function
   that WRITES, so everything that follows the scroll position costs one style recalculation per frame together. The loop stops once nothing is still
   catching up and shortly after scrolling stopped.

   Vue integration: the v-fx directive (./directive.ts) registers and unregisters elements; new elements are measured
   together in one microtask, before the browser paints, so a freshly mounted page never flashes fully visible. */
import type { MotionLevel } from '@/shared/types'
import { onFrame, wake, __resetFrames, type Write } from '@/shared/frame'
import { chase, clamp, drift, MAX_STAGGER, round3, shape, spine, stateOf, TALL, target, type Chase, type FxState } from './math'

const INTRO_DELAY = 140      // first entrance of a page head: start after this many ms ...
const INTRO_STEP = 90        // ... plus this much per step (data-fx-intro="n")
const INTRO_DURATION = 700
const OPEN_WINDOW = 500      // content that arrives this long after a page's head (the article body, ...) still belongs to the page opening
const OPEN_STEP = 0.7        // ... and in-view content enters one after another, this many head-steps apart (top to bottom, left to right)
const OPEN_LATEST = 960      // nothing waits longer than this to start, however much there is on the first screen
const LATE_STEP = 45         // content that appears later on its own (a new filter result, more moments): a quick staggered entrance
const LATE_LATEST = 360
const LATE_DURATION = 520

export const MODES: readonly MotionLevel[] = ['full', 'soft', 'off']
export const MOTION_KEY = 'bb:motion'

interface Item {
  el: HTMLElement
  type: string
  top: number
  h: number
  tall: boolean
  hidden: boolean
  in: number          // what is shown (eased, written to --fx-in)
  out: number
  lin: number         // the shown value before easing; -1 until the element has had its first picture
  lout: number
  lv: number          // the speed it is moving at (units per second), for the smooth chase
  lov: number
  nIn: number         // what the coming write phase will set
  nOut: number
  nD: number
  nState: FxState | ''
  tin: number         // where the scroll position says it should be (not eased)
  tout: number
  d: number
  state: FxState | ''
  stagI: number
  stagN: number
  forced: boolean
  introN: number | null          // data-fx-intro, until the element is first placed (see flush)
  seen: boolean                  // has been placed once: later flushes (switching motion back on) must not replay its entrance
  intro: { start: number; dur: number } | null
  sticky: HTMLElement | null
  local: number
  tag: HTMLElement | null
}

interface Env {
  now: () => number
  scrollY: () => number
  viewportHeight: () => number
}

const root = typeof document !== 'undefined' ? document.documentElement : (null as unknown as HTMLElement)

const S = {
  items: [] as Item[],
  map: new WeakMap<Element, Item>(),
  pending: [] as Item[],
  vh: 0,
  mode: 'full' as MotionLevel,
  siteMode: 'full' as MotionLevel,
  ready: false,
  started: false,
  dbg: false,
  frameMs: 0,
  frames: 0,
  stop: null as (() => void) | null,   // leaves the shared frame loop
  openUntil: 0,       // a page was opened (its head registered) and its content is still arriving until this time
  openIntro: false,   // ... and it was opened at the top, so its first screen plays an entrance
  openRank: 0,        // the next step number for in-view content of the page that is opening
  moving: false,      // some element has not yet caught up with its target
  measureQ: 0,
  flushQ: false,
  rotFlip: 1,
}

const env: Env = {
  now: () => performance.now(),
  scrollY: () => Math.max(0, window.scrollY || window.pageYOffset || 0),
  viewportHeight: () => root.clientHeight || window.innerHeight,
}

/** Tests replace the clock and the viewport; the page never calls this. */
export function __setEnv(patch: Partial<Env>): void {
  Object.assign(env, patch)
}

/* ---------------------------------------------------------------- mode */
/** The motion level for this visitor: the system "reduce motion" setting wins, then ?motion=, then the visitor's saved choice, then the site default. */
export function readMode(siteDefault: MotionLevel = 'full'): MotionLevel {
  let m: string = siteDefault
  try {
    m = new URLSearchParams(location.search).get('motion') || localStorage.getItem(MOTION_KEY) || siteDefault
  } catch { /* storage is optional */ }
  if (!MODES.includes(m as MotionLevel)) m = siteDefault
  if (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) m = 'off'
  return m as MotionLevel
}

function applyMode(): void {
  root.dataset.fxMode = S.mode
  root.classList.toggle('fx-off', S.mode === 'off')
}

/* ---------------------------------------------------------------- registration and measuring */
function docTop(el: HTMLElement): number {
  let y = 0
  for (let e: Element | null = el; e instanceof HTMLElement; e = e.offsetParent) y += e.offsetTop
  return y
}

/** An element inside a position:sticky box moves with the box while it is stuck, so its document position is not a constant.
    For those the engine measures the (never transformed) sticky box each frame and adds the element's fixed offset inside it. */
function stickyAncestor(el: HTMLElement): HTMLElement | null {
  for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
    if (getComputedStyle(p).position === 'sticky') return p
  }
  return null
}

function offsetWithin(el: HTMLElement, box: HTMLElement): number {
  let y = 0
  for (let e: Element | null = el; e instanceof HTMLElement && e !== box; e = e.offsetParent) y += e.offsetTop
  return y
}

function measureItem(it: Item): void {
  const el = it.el
  it.hidden = el.offsetParent === null && getComputedStyle(el).position !== 'fixed'
  if (it.hidden) return
  it.top = docTop(el)
  it.h = el.offsetHeight
  it.tall = it.h > S.vh * TALL
  if (it.sticky) {
    // the sticky box must be in this element's offsetParent chain; if it is not, fall back to the plain document position
    let inChain = false
    for (let e = el.offsetParent; e; e = (e as HTMLElement).offsetParent) if (e === it.sticky) { inChain = true; break }
    if (inChain) it.local = offsetWithin(el, it.sticky)
    else it.sticky = null
  }
}

function assignStagger(): void {
  // children of [data-fx-stagger] containers are staggered by their column inside each visual row
  document.querySelectorAll<HTMLElement>('[data-fx-stagger]').forEach((box) => {
    const kids = [...box.querySelectorAll<HTMLElement>(':scope > [data-fx], :scope > * > [data-fx]')]
      .map((el) => S.map.get(el))
      .filter((it): it is Item => !!it && !it.hidden)
    const rows: { top: number; items: Item[] }[] = []
    for (const it of kids) {
      const row = rows.find((r) => Math.abs(r.top - it.top) < 12)
      if (row) row.items.push(it)
      else rows.push({ top: it.top, items: [it] })
    }
    for (const r of rows) {
      r.items.sort((a, b) => a.el.offsetLeft - b.el.offsetLeft)
      const n = Math.min(r.items.length, MAX_STAGGER + 1)
      r.items.forEach((it, i) => { it.stagI = Math.min(i, MAX_STAGGER); it.stagN = n })
    }
    if (box.hasAttribute('data-fx-alt')) kids.forEach((it, i) => it.el.style.setProperty('--fx-dx', i % 2 ? '1' : '-1'))
  })
}

function measureAll(): void {
  S.vh = env.viewportHeight()
  S.items.forEach(measureItem)
  assignStagger()
  schedule()
}

function queueMeasure(): void {
  if (S.measureQ) return
  S.measureQ = requestAnimationFrame(() => { S.measureQ = 0; measureAll() })
}

/* ---------------------------------------------------------------- the frame */
function setState(it: Item, state: FxState): void {
  if (it.state !== state) { it.state = state; it.el.setAttribute('data-fx-state', state) }
}

const stuck = new Map<HTMLElement, number>()   // sticky box -> its current top, read once per frame
function stickyTop(it: Item): number {
  const box = it.sticky as HTMLElement
  let t = stuck.get(box)
  if (t === undefined) { t = box.getBoundingClientRect().top; stuck.set(box, t) }
  return t + it.local
}

const cin: Chase = { x: 0, v: 0 }
const cout: Chase = { x: 0, v: 0 }

/** Work out what an element should look like now. Writes nothing to the page: elements whose picture changed are queued in `dirty` for the write phase. */
function update(it: Item, sy: number, vh: number, now: number, dt: number, dirty: Item[]): void {
  if (it.hidden) return
  if (it.type === 'drift') {
    const d = drift(it.top, it.h, sy, vh)
    if (d !== it.d) { it.nD = d; it.nIn = it.in; it.nOut = it.out; it.nState = it.state; dirty.push(it) }
    return
  }
  if (it.type === 'spine') {
    const goal = spine(it.top, it.h, sy, vh)
    if (it.lin < 0) { it.lin = goal; it.lv = 0 } else { cin.x = it.lin; cin.v = it.lv; chase(cin, goal, dt); it.lin = cin.x; it.lv = cin.v }
    if (it.lin !== goal) S.moving = true
    const p = round3(it.lin)
    if (p !== it.in || it.state !== 'active') { it.nIn = p; it.nOut = it.out; it.nD = it.d; it.nState = 'active'; dirty.push(it) }
    return
  }
  if (it.forced) { it.tin = 1; it.tout = 0 }
  else {
    const top = it.sticky ? stickyTop(it) : it.top - sy
    let introP = 1
    if (it.intro) {
      introP = clamp((now - it.intro.start) / it.intro.dur)
      if (introP >= 1) it.intro = null
    }
    const t = target(top, it.h, vh, it.tall, it.stagI, it.stagN, introP)
    it.tin = t.tin; it.tout = t.tout
  }
  if (it.forced || it.lin < 0) { it.lin = it.tin; it.lout = it.tout; it.lv = 0; it.lov = 0 }
  else {
    cin.x = it.lin; cin.v = it.lv; chase(cin, it.tin, dt); it.lin = cin.x; it.lv = cin.v
    cout.x = it.lout; cout.v = it.lov; chase(cout, it.tout, dt); it.lout = cout.x; it.lov = cout.v
  }
  if (it.lin !== it.tin || it.lout !== it.tout) S.moving = true
  const { in: a, out: b, state } = shape(it.lin, it.lout)
  if (a !== it.in || b !== it.out || state !== it.state) { it.nIn = a; it.nOut = b; it.nState = state; it.nD = it.d; dirty.push(it) }
}

/** Apply what `update` decided. Only elements whose picture changed are touched. */
function apply(it: Item): void {
  if (it.type === 'drift') {
    it.d = it.nD
    it.el.style.setProperty('--fx-d', String(it.d))
    setState(it, 'active')
    return
  }
  if (it.nIn !== it.in) { it.in = it.nIn; it.el.style.setProperty('--fx-in', String(it.in)); if (it.type === 'text' || it.type === 'mask') it.el.style.setProperty('--fx-tin', String(it.in)) }
  if (it.type !== 'spine' && it.nOut !== it.out) { it.out = it.nOut; it.el.style.setProperty('--fx-out', String(it.out)); if (it.type === 'text' || it.type === 'mask') it.el.style.setProperty('--fx-tout', String(it.out)) }
  if (it.nState) setState(it, it.nState)
  if (S.dbg && it.tag) {
    const t = `${it.type} in ${it.in.toFixed(2)} out ${it.out.toFixed(2)}`
    if (it.tag.textContent !== t) it.tag.textContent = t
  }
}

/** One frame of the motion: everything is read and computed here; the returned function does the writing (and says whether anything is still moving). */
function runFrame(now: number, dt: number): Write {
  const t0 = performance.now()
  const sy = env.scrollY()
  const vh = S.vh
  S.moving = false
  stuck.clear()
  // every layout read first (the loop runs the other readers before any writer)
  for (let i = 0; i < S.items.length; i += 1) { const it = S.items[i] as Item; if (it.sticky && !it.hidden) stickyTop(it) }
  const dirty: Item[] = []
  for (let i = 0; i < S.items.length; i += 1) update(S.items[i] as Item, sy, vh, now, dt, dirty)
  const busy = S.moving || S.items.some((it) => it.intro)
  return () => {
    for (let i = 0; i < dirty.length; i += 1) apply(dirty[i] as Item)
    S.frameMs = performance.now() - t0
    S.frames += 1
    return busy
  }
}

/** A frame right now, outside the loop: the first picture of new elements must exist before the browser paints. */
function frameNow(): void {
  runFrame(env.now(), 1000 / 60)()
}

function schedule(): void {
  if (!S.ready || S.mode === 'off') return
  S.stop ??= onFrame((now, dt) => runFrame(now, dt))
  wake()
}

function leaveLoop(): void { S.stop?.(); S.stop = null }

/* ---------------------------------------------------------------- focus safety: a focused element is never transparent */
function nearest(el: EventTarget | null): Item | null {
  for (let e = el as Element | null; e && e !== document.body; e = e.parentElement) {
    const it = S.map.get(e)
    if (it) return it
  }
  return null
}
/** Only things the keyboard can reach need the guarantee. An element with tabindex="-1" is focused by the app, never by Tab (the page title
    after a navigation): forcing it would skip its entrance. */
const tabbable = (t: EventTarget | null): boolean => !(t instanceof HTMLElement) || t.getAttribute('tabindex') !== '-1'
function onFocusIn(e: FocusEvent): void { const it = tabbable(e.target) ? nearest(e.target) : null; if (it) { it.forced = true; schedule() } }
function onFocusOut(e: FocusEvent): void { const it = tabbable(e.target) ? nearest(e.target) : null; if (it) { it.forced = false; schedule() } }

/* ---------------------------------------------------------------- items */
function flush(): void {
  S.flushQ = false
  if (S.mode === 'off' || !S.pending.length) { S.pending.length = 0; return }
  S.vh = env.viewportHeight()
  const batch = S.pending.slice()
  S.pending.length = 0
  const now = env.now()
  const sy = env.scrollY()
  let opened = false
  let lastStep = -1
  for (const it of batch) {
    // decided here, not when the directive registers the element: by now the app has put the page at its start position,
    // and a page opened at the top plays its entrance while one opened scrolled down (Back / Forward) does not
    if (it.introN !== null) {
      opened = true
      lastStep = Math.max(lastStep, it.introN)
      if (sy <= 8) it.intro = { start: now + INTRO_DELAY + it.introN * INTRO_STEP, dur: INTRO_DURATION }
      it.introN = null
    }
    measureItem(it)
  }
  assignStagger()
  if (opened) { S.openUntil = now + OPEN_WINDOW; S.openIntro = sy <= 8; S.openRank = lastStep + 1 }
  enterInView(batch, now, sy)
  batch.forEach((it) => { it.seen = true })
  schedule()
  frameNow()                // the first picture is computed before the browser paints
  queueMeasure()            // and once more after layout has settled (fonts, images)
}

/** Everything new that is already on screen enters, not only the page head: while a page is opening (head plus the content that arrives with it)
    the first screen plays one entrance, top to bottom and left to right, after the head; content that shows up later on its own gets a quick one.
    Anything still below the fold enters with the scroll, as always. A page restored at a scroll position (Back / Forward) just appears. */
function enterInView(batch: Item[], now: number, sy: number): void {
  const opening = now < S.openUntil
  if (opening && !S.openIntro) return
  const vh = S.vh
  const fresh = batch.filter((it) => {
    if (it.seen || it.intro || it.hidden || it.forced || it.type === 'drift' || it.type === 'spine') return false
    const top = it.top - sy                                   // (content inside a sticky box is judged by the box's place in the document: right for the first picture)
    if (top + it.h <= 0 || top >= vh) return false             // not on screen: above it is already behind, below it enters with the scroll
    return target(top, it.h, vh, it.tall, it.stagI, it.stagN, 1).tin > 0
  })
  fresh.sort((a, b) => (a.top - b.top) || (a.el.offsetLeft - b.el.offsetLeft))
  fresh.forEach((it, k) => {
    if (opening) {
      const step = S.openRank + k * OPEN_STEP
      const delay = Math.min(INTRO_DELAY + step * INTRO_STEP, OPEN_LATEST)
      it.intro = { start: now + delay, dur: INTRO_DURATION }
    } else {
      it.intro = { start: now + Math.min(k * LATE_STEP, LATE_LATEST), dur: LATE_DURATION }
    }
  })
  if (opening) S.openRank += fresh.length * OPEN_STEP
}

function enqueue(it: Item): void {
  S.pending.push(it)
  if (!S.flushQ) { S.flushQ = true; queueMicrotask(flush) }
}

export function register(el: HTMLElement): void {
  if (S.map.has(el)) return
  const type = el.dataset.fx || 'fade'
  const it: Item = {
    el, type, top: 0, h: 0, tall: false, hidden: false, in: -1, out: -1, lin: -1, lout: -1, lv: 0, lov: 0, nIn: -1, nOut: -1, nD: 9, nState: '', tin: 0, tout: 0, d: 9, state: '', stagI: 0, stagN: 1,
    forced: false, introN: null, seen: false, intro: null, sticky: null, local: 0, tag: null,
  }
  if (type !== 'drift' && type !== 'spine') it.sticky = stickyAncestor(el)
  if (type === 'pop' && !el.style.getPropertyValue('--fx-rot')) { el.style.setProperty('--fx-rot', String(3 * S.rotFlip)); S.rotFlip *= -1 }
  const introAttr = el.getAttribute('data-fx-intro')
  if (introAttr !== null) it.introN = parseInt(introAttr, 10) || 0
  S.map.set(el, it)
  S.items.push(it)
  enqueue(it)
}

function clearItem(it: Item): void {
  for (const p of ['--fx-in', '--fx-out', '--fx-d', '--fx-tin', '--fx-tout']) it.el.style.removeProperty(p)
  it.el.removeAttribute('data-fx-state')
  it.in = it.out = it.lin = it.lout = -1; it.lv = it.lov = 0; it.d = 9; it.state = ''
}

export function unregister(el: Element): void {
  const it = S.map.get(el)
  if (!it) return
  S.map.delete(el)
  const i = S.items.indexOf(it)
  if (i >= 0) S.items.splice(i, 1)
  const j = S.pending.indexOf(it)
  if (j >= 0) S.pending.splice(j, 1)
  it.tag?.remove()
}

/** Register every [data-fx] element inside a container (content that Vue does not render itself, e.g. v-html). */
export function adopt(container: ParentNode): void {
  container.querySelectorAll<HTMLElement>('[data-fx]').forEach(register)
}
export function release(container: ParentNode): void {
  container.querySelectorAll('[data-fx]').forEach(unregister)
}

/* ---------------------------------------------------------------- lifecycle */
export function init(siteDefault: MotionLevel = 'full'): void {
  S.siteMode = siteDefault
  S.mode = readMode(siteDefault)
  applyMode()
  if (S.mode === 'off') { root.classList.remove('fx-pending'); return }
  S.vh = env.viewportHeight()
  S.ready = true
  root.classList.add('fx-ready')
  if (!S.started) {
    S.started = true
    window.addEventListener('resize', queueMeasure, { passive: true })
    window.addEventListener('orientationchange', queueMeasure)
    window.addEventListener('load', queueMeasure)
    document.addEventListener('focusin', onFocusIn)
    document.addEventListener('focusout', onFocusOut)
    document.addEventListener('load', queueMeasure, true)   // images finishing change the layout above later items
    document.fonts?.ready.then(queueMeasure)
    if ('ResizeObserver' in window) new ResizeObserver(queueMeasure).observe(document.body)
  }
}

/** Lift the "hidden until positioned" guard: called once the first page has been mounted and its elements have their first values. */
export function reveal(): void {
  root.classList.remove('fx-pending')
}

export function refresh(): void {
  if (!S.ready) return
  S.items = S.items.filter((it) => { if (it.el.isConnected) return true; S.map.delete(it.el); return false })
  measureAll()
  schedule()
}

export function setMode(m: MotionLevel): void {
  if (!MODES.includes(m)) return
  try { localStorage.setItem(MOTION_KEY, m) } catch { /* storage is optional */ }
  const wasOff = S.mode === 'off'
  S.mode = readMode(S.siteMode)
  applyMode()
  if (S.mode === 'off') { S.items.forEach(clearItem); leaveLoop(); return }
  if (!S.ready) init(S.siteMode)               // the page was opened with motion off: start the engine now
  if (wasOff) { S.items.forEach(clearItem); S.items.forEach((it) => S.pending.push(it)); flush(); return }   // measured and placed before the next paint
  schedule()
}

export const getMode = (): MotionLevel => S.mode

export function debug(on: boolean): void {
  S.dbg = on
  S.items.forEach((it) => {
    if (!it.el.hasAttribute('data-fx-debug')) return
    if (on && !it.tag) { it.tag = document.createElement('span'); it.tag.className = 'fx-debug-tag'; it.el.append(it.tag) }
    if (!on && it.tag) { it.tag.remove(); it.tag = null }
  })
  schedule()
}

export function stats(): { items: number; active: number; frameMs: number; frames: number; vh: number; mode: MotionLevel; moving: boolean } {
  const active = S.items.filter((it) => it.state === 'active').length
  return { items: S.items.length, active, frameMs: Math.round(S.frameMs * 100) / 100, frames: S.frames, vh: S.vh, mode: S.mode, moving: S.moving }
}

/** For tests and the QA audits: the current numbers of an element. */
export function read(el: Element): Record<string, unknown> | null {
  const it = S.map.get(el)
  if (!it) return null
  return {
    type: it.type, in: it.in, out: it.out, lin: it.lin, lout: it.lout, tin: it.tin, tout: it.tout, state: it.state, top: it.top, h: it.h, tall: it.tall, hidden: it.hidden, forced: it.forced,
    sticky: !!it.sticky, local: it.local, intro: !!it.intro, stagI: it.stagI, stagN: it.stagN,
  }
}

/** Forget everything (tests). */
export function __reset(): void {
  S.items.forEach(clearItem)
  leaveLoop(); __resetFrames()
  S.items = []; S.pending = []; S.map = new WeakMap(); S.ready = false; S.flushQ = false; S.measureQ = 0; S.moving = false
}

export const FX = { init, reveal, register, unregister, adopt, release, refresh, setMode, getMode, debug, stats, read }
export type { FxState }
export { stateOf, round3 }
