<script setup lang="ts">
import { computed } from 'vue'
import type { Mood } from '@/shared/types'

const props = defineProps<{ mood: Mood | null }>()
const known = new Set(['happy', 'energy', 'calm', 'sleepy', 'think', 'moved', 'sulk', 'sick', 'party', 'daze'])
const id = computed(() => (props.mood && known.has(props.mood.id) ? props.mood.id : ''))
</script>

<template>
  <span v-if="mood && id" class="mood"><svg aria-hidden="true" focusable="false"><use :href="`#mood-${id}`" /></svg>{{ mood.label }}</span>
</template>
