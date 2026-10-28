<script setup lang="ts">
/* The menu is a thread with beads: one bead per entry, a heart that rides along the thread to the page being shown, and a pink thread tied to the bead the heart came from.
   `side`: a vertical thread on the left edge (wide screens). `bottom`: a horizontal thread in a bar along the bottom edge (phones and tablets).
   The look is CSS, the motion is a few numbers written to the nav element every frame by one job of the shared frame loop (public/thread.ts has the physics):
     --hy   where the heart is (bead units: bead k is at k)      --hs  how much the heart is stretched along its way
     --sa / --sb  where the pink thread starts and ends (bead units)
   so a scroll or a page change does not re-render the menu, and nothing is a CSS transition that would have to wait for the route: the heart is aimed at the new bead the moment
   a page change is decided (a click on a bead, a push past the page's edge that went far enough) and keeps moving while the page is still being fetched. */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import { onFrame, wake } from '@/shared/frame'
import type { NavItem } from '@/shared/types'
import { currentIndex, iconFor } from '../nav'
import { progressNow, trackProgress } from '../progress'
import { warmRoute } from '../router'
import { aim, atRest, endsAtRest, makeMotion, pink, place, placeEnds, settle, step, stretch } from '../thread'
import { getLean, pendingUrl, setPending } from '../threadstate'
import { openMore, openSearch, scrollToTop, reducedMotion } from '../ui'
import { ICONS } from '../icons'
import { site } from '../state'

const props = defineProps<{ items: NavItem[]; variant: 'side' | 'bottom'; label: string }>()
const route = useRoute()
const current = computed(() => currentIndex(props.items, route.path))
const style = computed(() => ({ '--n': Math.max(props.items.length, 1) }))
const nav = ref<HTMLElement | null>(null)
const currentLabel = computed(() => props.items[current.value]?.label ?? '')

const indexOf = (url: string | null): number => (url ? props.items.findIndex((it) => it.kind !== 'action' && it.url === url) : -1)
const REDUCED = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null

let stopMotion: (() => void) | null = null
let stopRead: (() => void) | null = null
let motion = makeMotion(Math.max(current.value, 0))
let lastCurrent = current.value
const shown = { hy: NaN, sa: NaN, sb: NaN, hs: NaN }

onMounted(() => {
  const el = nav.value                                                      // the first picture is right before the first frame: heart and thread on the current bead, no travelling
  if (el) { const at = Math.max(current.value, 0); el.style.setProperty('--hy', String(at)); el.style.setProperty('--sa', String(at)); el.style.setProperty('--sb', String(at)); el.style.setProperty('--hs', '1') }
  stopMotion = onFrame((_now, dt) => {
    const cur = current.value
    const pending = indexOf(pendingUrl.value)
    const target = pending >= 0 ? pending : Math.max(cur, 0)
    const leaning = getLean()
    const toward = leaning ? indexOf(leaning.url) : -1
    const lean = leaning && toward >= 0 && cur >= 0 ? (toward - cur) * leaning.amount : 0
    const calm = document.documentElement.classList.contains('fx-off') || !!REDUCED?.matches || reducedMotion()
    const read = progressNow()
    const last = props.items.length - 1
    const reach = props.variant === 'bottom' && cur === last ? 0.5 : 1       // the "next" of the last bead is the end of the bar, half a cell away
    const limit = props.variant === 'bottom' ? props.items.length - 0.5 : props.items.length
    return () => {
      const el = nav.value
      if (!el) return
      const still = calm || lastCurrent < 0 || cur < 0
      if (still) place(motion, target)                                       // no travelling: first paint, a page that is not in the menu, reduced motion
      else { aim(motion, target); step(motion, lean, dt / 1000) }
      lastCurrent = cur
      const want = pink(motion, Math.max(cur, 0), cur < 0 ? 0 : read.shown, reach)
      const pk = still ? placeEnds(motion, want) : settle(motion, want, dt / 1000)
      const next = { hy: motion.heart.x, sa: Math.max(pk.from, 0), sb: Math.min(pk.to, limit), hs: calm ? 1 : stretch(motion.heart.v) }
      if (Math.abs(next.hy - shown.hy) > 1e-4 || Number.isNaN(shown.hy)) { el.style.setProperty('--hy', next.hy.toFixed(4)); shown.hy = next.hy }
      if (Math.abs(next.sa - shown.sa) > 1e-4 || Number.isNaN(shown.sa)) { el.style.setProperty('--sa', next.sa.toFixed(4)); shown.sa = next.sa }
      if (Math.abs(next.sb - shown.sb) > 1e-4 || Number.isNaN(shown.sb)) { el.style.setProperty('--sb', next.sb.toFixed(4)); shown.sb = next.sb }
      if (Math.abs(next.hs - shown.hs) > 1e-3 || Number.isNaN(shown.hs)) { el.style.setProperty('--hs', next.hs.toFixed(3)); shown.hs = next.hs }
      return !atRest(motion, lean) || !endsAtRest(motion, want)
    }
  })
  // "the page has been read to its end": the next bead gives a little tug (set straight on the element, not through Vue)
  stopRead = trackProgress((p) => { nav.value?.toggleAttribute('data-done', current.value >= 0 && p.raw >= 0.98) })
})
watch([current, pendingUrl, () => props.items.length], () => wake())
watch(() => route.path, () => setPending(null))                              // the page has changed (or went somewhere else): nothing is pending any more
onBeforeUnmount(() => { stopMotion?.(); stopRead?.() })

function act(item: NavItem): void {
  if (item.action === 'search') openSearch()
  else if (item.action === 'more') openMore()
  else if (item.action === 'top') scrollToTop()
}

/* pointing at a bead, or touching it, is the first sign that the visitor is going there: the page's data is asked for now, and a click aims the heart at once */
function ahead(item: NavItem): void {
  if (item.kind !== 'action' && !item.external && item.url.startsWith('/')) void warmRoute(item.url)
}
function beadClick(e: MouseEvent, item: NavItem, i: number): void {
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || item.external || i === current.value) return
  setPending(item.url)
}
</script>

<template>
  <nav ref="nav" class="thread" :class="[variant === 'side' ? 'nav thread--side' : 'tabbar thread--bottom', { 'has-cur': current >= 0 }]" :style="style" :aria-label="label">
    <span class="thread__line" aria-hidden="true" />
    <span class="thread__stitch" aria-hidden="true"><i class="thread__sew" /><i class="thread__tip" /></span>
    <span class="thread__pin" aria-hidden="true" />
    <span class="thread__knot" :class="{ 'is-next': current === items.length - 1 }" aria-hidden="true" />
    <template v-for="(item, i) in items" :key="`${item.kind}:${item.url}:${item.label}`">
      <button v-if="item.kind === 'action'" type="button" class="thread__bead" :style="{ '--k': i }" :aria-label="item.label" @click="act(item)">
        <span class="thread__dot"><Icon :name="iconFor(item, ICONS)" /></span>
        <span class="thread__tag">{{ item.label }}</span>
      </button>
      <NavLink
        v-else class="thread__bead" :class="{ 'is-next': i === current + 1 }" :style="{ '--k': i }" :aria-label="item.label" :to="item.url" :external="item.external" :current="i === current"
        @pointerenter="ahead(item)" @pointerdown="ahead(item)" @focus="ahead(item)" @touchstart.passive="ahead(item)" @click="beadClick($event, item, i)"
      >
        <span class="thread__dot"><Icon :name="iconFor(item, ICONS)" /></span>
        <span class="thread__tag">{{ item.label }}</span>
      </NavLink>
    </template>
    <button v-if="variant === 'side' && site.features.search" type="button" class="thread__search" aria-label="搜索（快捷键 /）" title="搜索（快捷键 /）" @click="openSearch"><Icon name="search" /></button>
    <span class="thread__heart" aria-hidden="true">
      <span class="thread__body"><Icon name="heart" /></span>
      <span :key="current" class="thread__label">{{ currentLabel }}</span>
    </span>
  </nav>
</template>
