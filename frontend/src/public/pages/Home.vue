<script setup lang="ts">
import { computed } from 'vue'
import type { PageState } from '../state'
import HeroBlock from './home/HeroBlock.vue'
import MomentsBlock from './home/MomentsBlock.vue'
import NoticeBar from './home/NoticeBar.vue'
import PostsBlock from './home/PostsBlock.vue'

const props = defineProps<{ state: Extract<PageState, { kind: 'home' }> }>()
const blocks = computed(() => props.state.data.blocks)
</script>

<template>
  <div class="home">
    <template v-for="b in blocks" :key="b.type">
      <HeroBlock v-if="b.type === 'hero'" :config="b.config" />
      <NoticeBar v-else-if="b.type === 'notice'" :text="b.config.text" />
      <PostsBlock v-else-if="b.type === 'featured'" id="featured" :title="b.config.title" :posts="b.data.posts" layout="grid" />
      <PostsBlock v-else-if="b.type === 'latest_posts'" id="posts" :title="b.config.title" :intro="b.config.intro" :posts="b.data.posts" :layout="b.config.layout" />
      <MomentsBlock v-else-if="b.type === 'latest_moments'" id="moments" :title="b.config.title" :intro="b.config.intro" :moments="b.data.moments" />
    </template>
  </div>
</template>
