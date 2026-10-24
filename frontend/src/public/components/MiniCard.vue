<script setup lang="ts">
/* A small card: related posts, previous / next suggestions, the 404 page's "maybe you wanted these". */
import Phrase from '@/fx/Phrase'
import NavLink from '@/ui/components/NavLink.vue'
import type { PostMini } from '@/shared/types'
import { dot } from '../fmt'
import Cover from './Cover.vue'

defineProps<{ post: PostMini }>()
</script>

<template>
  <NavLink class="card card--mini" :to="post.url">
    <Cover :media="post.cover" :seed="post.title" sizes="(min-width: 1100px) 230px, 100vw" short />
    <div class="card__body">
      <h3 class="card__title"><Phrase :text="post.title" /></h3>
      <div class="card__meta meta"><span><time :datetime="post.published_at">{{ dot(post.published_at) }}</time></span></div>
    </div>
  </NavLink>
</template>
