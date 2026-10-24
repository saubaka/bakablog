<script setup lang="ts">
import { computed } from 'vue'
import NavLink from '@/ui/components/NavLink.vue'
import type { Tag } from '@/shared/types'

const props = defineProps<{ tag: Pick<Tag, 'name' | 'url' | 'color'>; count?: number }>()
const tone = computed(() => (props.tag.color === 'sky' || props.tag.color === 'rose' || props.tag.color === 'mist' ? `tag--${props.tag.color}` : ''))
</script>

<template>
  <NavLink class="tag" :class="tone" :to="tag.url">{{ tag.name }}<span v-if="count !== undefined" class="n">{{ count }}</span></NavLink>
</template>
