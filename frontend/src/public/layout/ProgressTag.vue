<script setup lang="ts">
/* How much of the page has been read, as a small tag on a thread at the right edge. The thread starts at the height of the menu's topmost pin on the left and the tag
   hangs on it, riding down as the page is read and up again when it is scrolled back. All of it is springs (shared/spring.ts) stepped in the shared frame loop: the tag
   follows the scroll with a little weight (a hard jump overshoots and settles), it is pulled sideways by the speed (swings), and it drops in from above the screen when
   a page has arrived (and on small screens each time scrolling starts, going away again a moment after it stops). Click it to go back to the top.
   Positions are written straight to the elements (CSSOM), not through Vue: a scroll does not re-render anything. */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { onFrame, wake } from '@/shared/frame'
import { stepSpring, type SpringState } from '@/shared/spring'
import { clamp01, geometry, IDLE_MS, MIN_ROOM, percent, swingTarget, tagY, wantShown, type Geometry } from '../hangtag'
import { site } from '../state'
import { reducedMotion, scrollToTop } from '../ui'

const root = ref<HTMLElement | null>(null)
const tag = ref<HTMLButtonElement | null>(null)
const swing = ref<HTMLElement | null>(null)
const num = ref<HTMLElement | null>(null)
const route = useRoute()

const NARROW = typeof matchMedia === 'function' ? matchMedia('(max-width: 1100px)') : null
const MOTION = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null
const ARRIVE_MS = 520          // a new page needs this long to come in before the tag drops
const RING = 3.5               // the point of the line is the middle of the ring (half its height)

let stop: (() => void) | null = null
let armTimer = 0
let armed = false
let dirty = true
let geo: Geometry = { top: 28, len: 300 }
let pos: SpringState = { x: 0, v: 0 }
let ang: SpringState = { x: 0, v: 0 }
let drop: SpringState = { x: 1, v: 0 }
let lastY = -1
let lastMove = -1e9
let lastText = ''
let away = true
let ro: ResizeObserver | null = null

function arm(): void { armed = true; dirty = true; wake() }
function disarm(): void { armed = false; window.clearTimeout(armTimer); armTimer = window.setTimeout(arm, ARRIVE_MS); wake() }
function invalidate(): void { dirty = true; wake() }

function measure(): Geometry {
  const pin = document.querySelector('.thread--side .thread__pin')?.getBoundingClientRect()
  const bar = document.querySelector('.thread--bottom')?.getBoundingClientRect()
  const fab = document.querySelector('.toc-fab')?.getBoundingClientRect()
  let floor = window.innerHeight
  if (bar && bar.height > 0) floor = Math.min(floor, bar.top)
  if (fab && fab.height > 0) floor = Math.min(floor, fab.top)
  return geometry(pin && pin.width > 0 ? pin.top + pin.height / 2 : null, floor)
}

onMounted(() => {
  armTimer = window.setTimeout(arm, ARRIVE_MS + 200)
  window.addEventListener('resize', invalidate, { passive: true })
  ro = typeof ResizeObserver === 'function' ? new ResizeObserver(() => wake()) : null   // the page got longer or shorter (pictures arrived): the progress changes without a scroll
  ro?.observe(document.body)
  stop = onFrame((now, dt) => {
    const room = document.documentElement.scrollHeight - window.innerHeight
    const sy = window.scrollY
    const raw = room > 24 ? clamp01(sy / room) : 0
    if (sy !== lastY) { lastY = sy; lastMove = now }
    const narrow = !!NARROW?.matches
    const want = wantShown({ armed, room, narrow, sinceScroll: now - lastMove })
    const calm = document.documentElement.classList.contains('fx-off') || !!MOTION?.matches || reducedMotion()
    let fresh: Geometry | null = null
    if (dirty) { fresh = measure(); dirty = false }
    return () => {
      const el = tag.value
      if (!el || !swing.value || !num.value || !root.value) return
      if (fresh) {
        geo = fresh
        root.value.style.setProperty('--pt-top', `${geo.top.toFixed(1)}px`)
        root.value.style.setProperty('--pt-len', `${geo.len.toFixed(1)}px`)
      }
      const s = dt / 1000
      const goal = want ? 0 : 1
      if (calm) { pos = { x: raw, v: 0 }; ang = { x: 0, v: 0 }; drop = { x: goal, v: 0 } }
      else {
        pos = stepSpring(pos, raw, s, { stiffness: 80, damping: 11 })
        ang = stepSpring(ang, swingTarget(pos.v), s, { stiffness: 150, damping: 8 })
        drop = stepSpring(drop, goal, s, want ? { stiffness: 90, damping: 9 } : { stiffness: 160, damping: 22 })
      }
      el.style.translate = `0 ${(tagY(geo, pos.x, drop.x) - RING).toFixed(1)}px`
      swing.value.style.rotate = `${ang.x.toFixed(2)}deg`
      root.value.style.opacity = clamp01(1 - drop.x * 1.5).toFixed(3)
      const text = percent(pos.x)
      if (text !== lastText) { lastText = text; num.value.textContent = text }
      const gone = drop.x > 0.97
      if (gone !== away) { away = gone; el.toggleAttribute('inert', gone); root.value.toggleAttribute('data-away', gone) }
      const moving = Math.abs(pos.x - raw) > 0.0004 || Math.abs(pos.v) > 0.002 || Math.abs(ang.x) > 0.04 || Math.abs(ang.v) > 0.3 || Math.abs(drop.x - goal) > 0.002 || Math.abs(drop.v) > 0.02
      return moving || (narrow && armed && room > MIN_ROOM && now - lastMove < IDLE_MS + 60)
    }
  })
})

watch(() => route.path, disarm)
watch(() => site.value.nav.top.length, invalidate)
onBeforeUnmount(() => {
  stop?.()
  ro?.disconnect()
  window.clearTimeout(armTimer)
  window.removeEventListener('resize', invalidate)
})
</script>

<template>
  <div ref="root" class="ptag" data-away>
    <span class="ptag__line" aria-hidden="true" />
    <button ref="tag" class="ptag__tag" type="button" aria-label="回到顶部" inert @click="scrollToTop">
      <span ref="swing" class="ptag__swing">
        <i class="ptag__ring" />
        <i class="ptag__string" />
        <span class="ptag__pill" aria-hidden="true"><b ref="num" /></span>
      </span>
    </button>
  </div>
</template>
