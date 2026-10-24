/* Turning the page by scrolling past its edge.
   At the very bottom of a page, keep pushing and the next entry of the menu opens; at the very top, keep pushing and the previous one does. Nothing before the first entry and
   nothing after the last. The page itself is the thing being pushed: it follows the finger / wheel like a stretched rubber band (it slows down and never goes far), a hint shows
   where the push leads (the heart bead of the menu leans towards that entry; there is no label or card on the screen). Let go early and it springs back; push far enough and it is thrown off the screen, the next page
   is already on its way (it was asked for while the push was under way) and rises from the other side with a little weight. All of it is spring physics (shared/spring.ts):
   the speed of the hand is kept, and nothing has a fixed duration.

   A push only counts when it starts at the edge: a wheel / trackpad burst that happened to scroll the page to its end (including its momentum) is an ordinary scroll, the next
   burst after a pause is a push. A touch counts when the finger went down while the page was already at the edge. Overlays, inner scrolling boxes, pinch zoom, the "off" motion
   level and the system's "reduce motion" all switch it off; the menu is always there as the plain way to change page. */
import { ref } from 'vue'
import type { Router } from 'vue-router'
import { rubber, spring, unrubber, type SpringRun } from '@/shared/spring'
import type { NavItem } from '@/shared/types'
import { lightbox } from './lightbox'
import { adjacentLink } from './nav'
import { warmRoute } from './router'
import { site } from './state'
import { moreOpen, searchOpen } from './ui'
import { TABLET } from './viewport'

/** True from the moment a page is let go until the new one has settled: the router swaps pages at once then (the page itself is already out of sight). */
export const turning = ref(false)

const THRESHOLD = 140     // how far (px of push) it takes to turn the page
const LIMIT = 120         // the most the page is ever pulled out of its place
const WHEEL_GAIN = 0.85   // push per px of wheel travel
const GAP = 90            // ms without a wheel event: the next one starts a new push
const RELEASE = 260       // ms without a wheel event: the push is over, let go
const TOUCH_SLACK = 6     // px of finger travel before it counts as a push

let stage: HTMLElement | null = null
let router: Router | null = null
let raw = 0               // the push, signed: > 0 past the bottom, < 0 past the top
let curY = 0              // where the page is now (px, positive = down)
let run: SpringRun | null = null
let busy = false
let armed = false
let lastWheel = -1e9
let releaseTimer = 0
let finger: { y0: number; atTop: boolean; atBottom: boolean; active: boolean; dir: 1 | -1; y: number; t: number; v: number } | null = null

const root = typeof document !== 'undefined' ? document.documentElement : (null as unknown as HTMLElement)
const atTop = (): boolean => window.scrollY <= 0
const atBottom = (): boolean => window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 1
const menu = (): NavItem[] => (window.matchMedia(`(max-width: ${TABLET}px)`).matches ? site.value.nav.mobile : site.value.nav.top)
const neighbour = (dir: 1 | -1): ReturnType<typeof adjacentLink> => (router ? adjacentLink(menu(), router.currentRoute.value.path, dir) : null)

function allowed(): boolean {
  if (busy || !stage || !router) return false
  if (root.classList.contains('fx-off')) return false
  if (searchOpen.value || moreOpen.value || lightbox.value) return false
  return !document.querySelector('dialog[open], .sheet.is-open')
}

/** Is something under the pointer that can still scroll in this direction (a long code block, a text box)? Then the wheel belongs to it. */
function innerScrolls(target: EventTarget | null, dy: number): boolean {
  for (let e = target as HTMLElement | null; e && e !== document.body && e !== root; e = e.parentElement) {
    const oy = getComputedStyle(e).overflowY
    if ((oy === 'auto' || oy === 'scroll') && e.scrollHeight > e.clientHeight + 1) {
      if (dy > 0 && e.scrollTop + e.clientHeight < e.scrollHeight - 1) return true
      if (dy < 0 && e.scrollTop > 0) return true
    }
  }
  return false
}

/* ---- the page follows the push ------------------------------------------------------------------------------------------------------ */
function place(y: number): void {
  curY = y
  if (!stage) return
  if (Math.abs(y) < 0.05 && !turning.value) { stage.style.removeProperty('translate'); stage.style.removeProperty('opacity'); return }
  const vh = window.innerHeight
  stage.style.translate = `0 ${y.toFixed(2)}px`
  const away = Math.min(Math.abs(y) / (vh * 0.62), 1)
  stage.style.opacity = String(Math.round((1 - 0.96 * away * away * (3 - 2 * away)) * 1000) / 1000)   // fades only once it is well on its way
}

const visual = (): number => -Math.sign(raw) * rubber(Math.abs(raw), LIMIT)

function show(): void {
  const dir = raw > 0 ? 1 : raw < 0 ? -1 : 0
  const n = dir ? neighbour(dir) : null
  const progress = Math.min(Math.abs(raw) / THRESHOLD, 1)
  // the heart bead of the menu leans towards the entry the push leads to
  const lean = n ? dir * progress * 0.6 * Math.abs(n.index - n.from) : 0
  root.style.setProperty('--pull-nav', lean.toFixed(3))
  root.classList.toggle('is-pulling', dir !== 0)
  root.removeAttribute('data-pull')
  place(visual())
  if (n && progress > 0.3) warmRoute(n.item.url)
}

/** Let go without turning: the page and the heart spring back, keeping the speed of the hand. */
function snapBack(velocity = 0): void {
  window.clearTimeout(releaseTimer)
  const from = curY
  raw = 0
  armed = false
  root.dataset.pull = 'back'
  root.style.setProperty('--pull-nav', '0')
  run?.stop()
  run = spring(from, 0, (y) => { place(y) }, { stiffness: 280, damping: 26, velocity })
  void run.done.then(() => {
    if (busy) return
    place(0)
    root.classList.remove('is-pulling')
    root.removeAttribute('data-pull')
  })
}

/** Far enough: throw the page off the screen, open the next one while it is out of sight, bring that one up from the other side. */
async function turn(dir: 1 | -1, velocity = 0): Promise<void> {
  const n = neighbour(dir)
  if (!n || !router) { snapBack(velocity); return }
  window.clearTimeout(releaseTimer)
  busy = true
  turning.value = true
  root.classList.add('is-turning')
  root.removeAttribute('data-pull')
  warmRoute(n.item.url)
  const vh = window.innerHeight
  run?.stop()
  run = spring(curY, -dir * (vh + 60), (y) => { place(y); return Math.abs(y) >= vh }, { stiffness: 170, damping: 30, velocity: -dir * Math.max(Math.abs(velocity), 700) })
  await run.done
  try { await router.push(n.item.url) } catch { /* the page that opens reports its own trouble */ }
  await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))   // the new page is in the document now, hidden
  root.style.setProperty('--pull-nav', '0')
  const from = dir * vh * 0.55
  place(from)
  run = spring(from, 0, (y) => { place(y) }, { stiffness: 190, damping: 23 })
  await run.done
  turning.value = false
  place(0)
  root.classList.remove('is-pulling', 'is-turning')
  raw = 0
  armed = false
  busy = false
}

/* ---- wheel and trackpad -------------------------------------------------------------------------------------------------------------- */
function onWheel(e: WheelEvent): void {
  if (e.ctrlKey || e.metaKey || !allowed()) return
  const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * window.innerHeight : e.deltaY
  if (dy === 0 || Math.abs(e.deltaX) > Math.abs(dy)) return
  const dir: 1 | -1 = dy > 0 ? 1 : -1
  const fresh = e.timeStamp - lastWheel > GAP
  lastWheel = e.timeStamp
  if (fresh) {
    if (raw !== 0) armed = Math.sign(raw) === dir                              // the next notch of a push that is still going
    else armed = (dir === 1 ? atBottom() : atTop()) && !innerScrolls(e.target, dy) && !!neighbour(dir)
  }
  if (!armed) return
  const next = raw + dy * WHEEL_GAIN
  if (raw !== 0 && Math.sign(next) !== Math.sign(raw)) { armed = false; snapBack(); return }   // pushed back to the edge and past it the other way: an ordinary scroll again
  e.preventDefault()
  raw = raw === 0 ? dir * Math.abs(dy) * WHEEL_GAIN : next
  show()
  if (Math.abs(raw) >= THRESHOLD) { void turn(raw > 0 ? 1 : -1); return }
  window.clearTimeout(releaseTimer)
  releaseTimer = window.setTimeout(() => { if (raw !== 0 && !busy) snapBack() }, RELEASE)
}

/* ---- touch --------------------------------------------------------------------------------------------------------------------------- */
function onTouchStart(e: TouchEvent): void {
  if (e.touches.length !== 1 || !allowed()) { finger = null; return }
  const y = e.touches[0]!.clientY
  finger = { y0: y, atTop: atTop(), atBottom: atBottom(), active: false, dir: 1, y, t: e.timeStamp, v: 0 }
  if (raw !== 0 || curY !== 0) {                                               // the finger came down on a page that is still springing back: pick it up where it is
    run?.stop()
    window.clearTimeout(releaseTimer)
    raw = Math.sign(-curY) * unrubber(Math.abs(curY), LIMIT)
  }
}

function onTouchMove(e: TouchEvent): void {
  const f = finger
  if (!f || e.touches.length !== 1) return
  const y = e.touches[0]!.clientY
  const dt = Math.max(e.timeStamp - f.t, 1)
  f.v = f.v * 0.6 + ((y - f.y) / dt) * 1000 * 0.4
  f.y = y
  f.t = e.timeStamp
  const dy = y - f.y0
  if (!f.active) {
    if (Math.abs(dy) < TOUCH_SLACK) return
    const dir: 1 | -1 = dy < 0 ? 1 : -1                                        // the finger going up pushes past the bottom
    if (!(dir === 1 ? f.atBottom : f.atTop) || !neighbour(dir)) { finger = null; return }   // an ordinary scroll
    f.active = true
    f.dir = dir
  }
  const push = (f.dir === 1 ? -dy : dy) - TOUCH_SLACK
  if (e.cancelable) e.preventDefault()
  raw = f.dir * Math.max(push, 0)
  show()
}

function onTouchEnd(): void {
  const f = finger
  finger = null
  if (!f?.active) return
  const speed = f.dir === 1 ? -f.v : f.v                                       // px/s in the direction of the push
  if (Math.abs(raw) >= THRESHOLD * 0.8 || (speed > 900 && Math.abs(raw) > 40)) void turn(f.dir, f.v)
  else snapBack(f.v)
}

/** Start listening. `el` is what moves (the page and the foot of it); returns a function that stops everything. */
export function startPull(el: HTMLElement, r: Router): () => void {
  stage = el
  router = r
  const opts: AddEventListenerOptions = { passive: false }
  window.addEventListener('wheel', onWheel, opts)
  window.addEventListener('touchstart', onTouchStart, { passive: true })
  window.addEventListener('touchmove', onTouchMove, opts)
  window.addEventListener('touchend', onTouchEnd, { passive: true })
  window.addEventListener('touchcancel', onTouchEnd, { passive: true })
  return () => {
    window.removeEventListener('wheel', onWheel)
    window.removeEventListener('touchstart', onTouchStart)
    window.removeEventListener('touchmove', onTouchMove)
    window.removeEventListener('touchend', onTouchEnd)
    window.removeEventListener('touchcancel', onTouchEnd)
    run?.stop()
    window.clearTimeout(releaseTimer)
    stage?.style.removeProperty('translate')
    stage?.style.removeProperty('opacity')
    stage = null
    router = null
  }
}
