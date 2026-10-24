<script setup lang="ts">
/* Back to top: an arrow with a progress ring that fills as the page is read. The ring and the "shown" state are written by the frame loop (smoothed), not through Vue. */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import Icon from '@/ui/components/Icon'
import { trackProgress } from '../progress'
import { scrollToTop } from '../ui'

const R = 27
const C = 2 * Math.PI * R
const root = ref<HTMLElement | null>(null)
const arc = ref<SVGCircleElement | null>(null)
let stop: (() => void) | null = null
let on = false

onMounted(() => {
  stop = trackProgress((p) => {
    arc.value?.setAttribute('stroke-dashoffset', (C * (1 - p.shown)).toFixed(2))
    const now = p.scrollY > 600
    if (now !== on && root.value) {
      on = now
      root.value.classList.toggle('is-on', now)
      if (now) root.value.removeAttribute('inert'); else root.value.setAttribute('inert', '')
    }
  })
})
onBeforeUnmount(() => stop?.())
</script>

<template>
  <div ref="root" class="backtop" inert>
    <button class="ring-btn" type="button" aria-label="回到顶部" @click="scrollToTop">
      <svg class="ring" viewBox="0 0 58 58" aria-hidden="true"><circle cx="29" cy="29" :r="R" stroke="var(--line)" /><circle ref="arc" cx="29" cy="29" :r="R" stroke="var(--rose-300)" :stroke-dasharray="C" :stroke-dashoffset="C" /></svg>
      <Icon name="arrow-u" />
    </button>
  </div>
</template>
