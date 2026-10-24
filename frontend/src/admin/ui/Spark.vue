<script setup lang="ts">
/* One thin line of numbers (visits per day). Light blue like everything else; no axes, the numbers are written next to it. */
import { computed } from 'vue'

const props = withDefaults(defineProps<{ values: number[]; label: string; height?: number }>(), { height: 36 })
const path = computed(() => {
  const v = props.values
  if (v.length < 2) return ''
  const max = Math.max(...v, 1)
  const w = 100
  const h = 30
  return v.map((n, i) => `${i === 0 ? 'M' : 'L'}${((i / (v.length - 1)) * w).toFixed(2)} ${(h - 2 - (n / max) * (h - 6)).toFixed(2)}`).join(' ')
})
</script>

<template>
  <svg class="adm-spark" viewBox="0 0 100 30" preserveAspectRatio="none" role="img" :aria-label="label" :height="height">
    <path v-if="path" :d="path" fill="none" stroke="var(--sky-300)" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round" />
  </svg>
</template>
