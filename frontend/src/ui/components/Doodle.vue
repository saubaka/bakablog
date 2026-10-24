<script setup lang="ts">
/* A line doodle that drifts a little against the scroll. The wrapper is an HTML element because the engine measures with offsetTop. */
import { vFx } from '@/fx/directive'

defineProps<{ name: string; drift?: number }>()
</script>

<template>
  <span class="doodle-box" v-fx="{ type: 'drift', drift: drift ?? 24 }" aria-hidden="true">
    <svg class="doodle" focusable="false"><use :href="`#d-${name}`" /></svg>
  </span>
</template>
