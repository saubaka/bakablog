<script setup lang="ts">
/* A post's picture, or a quiet generated pattern when it has none. Never requests anything it does not need:
   the placeholder colour is shown first, the picture is lazy and sized by srcset. */
import { computed } from 'vue'
import { coverClasses } from '@/shared/cover'
import type { Media } from '@/shared/types'

const props = withDefaults(defineProps<{
  media: Media | null
  alt?: string
  focus?: { x: number; y: number } | null
  seed: string
  sizes?: string
  eager?: boolean
  short?: boolean
}>(), { alt: '', focus: null, sizes: '(min-width: 1100px) 360px, 100vw', eager: false, short: false })

const generated = computed(() => coverClasses(props.seed))
const style = computed(() => (props.media?.color ? { backgroundColor: props.media.color } : undefined))
const position = computed(() => (props.focus ? { objectPosition: `${Math.round(props.focus.x * 100)}% ${Math.round(props.focus.y * 100)}%` } : undefined))
</script>

<template>
  <div class="cover" :class="[media ? '' : generated, { 'cover--short': short }]" :style="style">
    <img v-if="media" :src="media.src" :srcset="media.srcset || undefined" :sizes="media.srcset ? sizes : undefined" :width="media.width" :height="media.height" :alt="alt || media.alt" :loading="eager ? 'eager' : 'lazy'" decoding="async" :style="position">
    <slot />
  </div>
</template>
