<script setup lang="ts">
/* The visitor's own motion level (standard / soft / off). The system's "reduce motion" setting always wins and is said out loud. */
import { ref } from 'vue'
import { getMode, setMode } from '@/fx/engine'
import type { MotionLevel } from '@/shared/types'

const mode = ref<MotionLevel>(getMode())
const system = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
const options: { id: MotionLevel; label: string }[] = [
  { id: 'full', label: '标准' },
  { id: 'soft', label: '轻柔' },
  { id: 'off', label: '关闭' },
]

function pick(m: MotionLevel): void {
  setMode(m)
  mode.value = getMode()
}
</script>

<template>
  <div class="motion-switch" role="group" aria-label="滚动动效">
    <span class="label">滚动动效</span>
    <div class="motion-switch__row">
      <button v-for="o in options" :key="o.id" type="button" class="tag" :aria-pressed="mode === o.id" :disabled="system && o.id !== 'off'" @click="pick(o.id)">{{ o.label }}</button>
    </div>
    <small v-if="system">系统开启了「减少动态效果」，所以动效保持关闭。</small>
  </div>
</template>
