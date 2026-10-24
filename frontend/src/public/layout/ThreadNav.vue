<script setup lang="ts">
/* The menu is a thread with beads: one bead per entry, a heart bead that rides along the thread to the page being shown, and a pink
   stitch that sews from the current bead towards the next one as the page is read (the knot at the end of the thread is "next" for the last page).
   `side`: a vertical thread on the left edge (wide screens). `bottom`: a horizontal thread in a bar along the bottom edge (phones and tablets).
   Positions are pure CSS from three numbers (--n entries, --i current, --p read), so nothing is measured and a resize cannot misplace anything;
   only a real navigation moves the heart (class is-moving), first paint and resizing do not. */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import type { NavItem } from '@/shared/types'
import { currentIndex, iconFor } from '../nav'
import { trackProgress } from '../progress'
import { openMore, openSearch, scrollToTop } from '../ui'
import { ICONS } from '../icons'

const props = defineProps<{ items: NavItem[]; variant: 'side' | 'bottom'; label: string }>()
const route = useRoute()
const current = computed(() => currentIndex(props.items, route.path))
const style = computed(() => ({
  '--n': Math.max(props.items.length, 1),
  '--i': Math.max(current.value, 0),
  '--last': current.value === props.items.length - 1 ? 1 : 0,
}))
const nav = ref<HTMLElement | null>(null)
const currentLabel = computed(() => props.items[current.value]?.label ?? '')

const moving = ref(false)
let timer = 0
watch(current, () => {
  moving.value = true
  window.clearTimeout(timer)
  timer = window.setTimeout(() => { moving.value = false }, 950)
})

/* --p (how much of the page has been read) and the "stitch finished" mark change on every frame of a scroll: they are written straight to the element by the frame loop
   (smoothed), not through Vue, so a scroll does not re-render the menu */
let stop: (() => void) | null = null
onMounted(() => {
  stop = trackProgress((p) => {
    const el = nav.value
    if (!el) return
    el.style.setProperty('--p', p.shown.toFixed(4))
    el.toggleAttribute('data-done', current.value >= 0 && p.raw >= 0.98)
  })
})
onBeforeUnmount(() => { stop?.(); window.clearTimeout(timer) })

function act(item: NavItem): void {
  if (item.action === 'search') openSearch()
  else if (item.action === 'more') openMore()
  else if (item.action === 'top') scrollToTop()
}
</script>

<template>
  <nav ref="nav" class="thread" :class="[variant === 'side' ? 'nav thread--side' : 'tabbar thread--bottom', { 'has-cur': current >= 0, 'is-moving': moving }]" :style="style" :aria-label="label">
    <span class="thread__line" aria-hidden="true" />
    <span class="thread__stitch" aria-hidden="true"><i class="thread__sew" /><i class="thread__tip" /></span>
    <span class="thread__pin" aria-hidden="true" />
    <span class="thread__knot" :class="{ 'is-next': current === items.length - 1 }" aria-hidden="true" />
    <template v-for="(item, i) in items" :key="`${item.kind}:${item.url}:${item.label}`">
      <button v-if="item.kind === 'action'" type="button" class="thread__bead" :style="{ '--k': i }" :aria-label="item.label" @click="act(item)">
        <span class="thread__dot"><Icon :name="iconFor(item, ICONS)" /></span>
        <span class="thread__tag">{{ item.label }}</span>
      </button>
      <NavLink v-else class="thread__bead" :class="{ 'is-next': i === current + 1 }" :style="{ '--k': i }" :aria-label="item.label" :to="item.url" :external="item.external" :current="i === current">
        <span class="thread__dot"><Icon :name="iconFor(item, ICONS)" /></span>
        <span class="thread__tag">{{ item.label }}</span>
      </NavLink>
    </template>
    <span class="thread__heart" aria-hidden="true">
      <Icon name="heart" />
      <span :key="current" class="thread__label">{{ currentLabel }}</span>
    </span>
  </nav>
</template>
