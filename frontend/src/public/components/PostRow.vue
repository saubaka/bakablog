<script setup lang="ts">
import Phrase from '@/fx/Phrase'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import type { PostCard } from '@/shared/types'
import Stamp from './Stamp.vue'

defineProps<{ post: PostCard; level?: 2 | 3; order?: number }>()
</script>

<template>
  <NavLink class="postrow" :to="post.url">
    <Stamp :iso="post.published_at" small />
    <div>
      <component :is="`h${level ?? 3}`" class="postrow__title"><Phrase :text="post.title" /></component>
      <p v-if="post.summary" class="postrow__sum">{{ post.summary }}</p>
      <div v-if="post.tags.length" class="postrow__tags"><span v-for="t in post.tags.slice(0, 4)" :key="t.id" class="tag tag--sky">{{ t.name }}</span></div>
    </div>
    <Icon name="arrow-r" class="postrow__go" />
  </NavLink>
</template>
