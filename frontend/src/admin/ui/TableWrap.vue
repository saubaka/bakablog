<script setup lang="ts">
/* A table that scrolls sideways when the screen is narrow. Only then does it become a keyboard stop (a scrollable area must be reachable without a mouse). */
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps<{ label: string }>()
const box = ref<HTMLElement | null>(null)
const scrolls = ref(false)
let ro: ResizeObserver | null = null
function measure(): void { if (box.value) scrolls.value = box.value.scrollWidth > box.value.clientWidth + 1 }
onMounted(() => {
  measure()
  if ('ResizeObserver' in window && box.value) { ro = new ResizeObserver(measure); ro.observe(box.value); if (box.value.firstElementChild) ro.observe(box.value.firstElementChild) }
})
onBeforeUnmount(() => ro?.disconnect())
</script>

<template>
  <div ref="box" class="adm-table-wrap" :tabindex="scrolls ? 0 : undefined" :role="scrolls ? 'region' : undefined" :aria-label="scrolls ? `${label}（可横向滚动）` : undefined"><slot /></div>
</template>
