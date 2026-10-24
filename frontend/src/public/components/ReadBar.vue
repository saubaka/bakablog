<script setup lang="ts">
/* The 2px reading line at the very top: how far through the article the visitor is. Written by the shared frame loop (smoothed), not through Vue;
   the article's place in the document is measured when the layout changes, a scroll only compares numbers. */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { chase, type Chase } from '@/fx/math'
import { onFrame } from '@/shared/frame'

const props = defineProps<{ target: HTMLElement | null }>()
const bar = ref<HTMLElement | null>(null)
const c: Chase = { x: 0, v: 0 }
let stop: (() => void) | null = null
let observer: ResizeObserver | null = null
let top = 0
let height = 1
let dirty = true
let first = true
let shownOn = false

const markDirty = (): void => { dirty = true }

onMounted(() => {
  stop = onFrame((_now, dt) => {
    const el = props.target
    if (!el) return
    if (dirty) { top = el.getBoundingClientRect().top + window.scrollY; height = Math.max(el.offsetHeight, 1); dirty = false }
    const v = Math.max(0, Math.min(1, (window.scrollY - top + window.innerHeight * 0.3) / height))
    if (first) { c.x = v; c.v = 0; first = false } else chase(c, v, dt)
    return () => {
      const b = bar.value
      if (!b) return
      b.style.setProperty('--p', c.x.toFixed(4))
      const on = v > 0.005 && v < 0.998
      if (on !== shownOn) { shownOn = on; b.classList.toggle('is-on', on) }
      return c.x !== v
    }
  })
  window.addEventListener('resize', markDirty, { passive: true })
  if ('ResizeObserver' in window) { observer = new ResizeObserver(markDirty); observer.observe(document.body) }
})
onBeforeUnmount(() => { stop?.(); window.removeEventListener('resize', markDirty); observer?.disconnect() })
</script>

<template>
  <div ref="bar" class="readbar" aria-hidden="true" />
</template>
