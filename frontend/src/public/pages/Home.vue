<script setup lang="ts">
import { computed } from 'vue'
import type { HomeBlock } from '@/shared/types'
import type { PageState } from '../state'
import AboutBlock from './home/AboutBlock.vue'
import HeroBlock from './home/HeroBlock.vue'
import MomentsBlock from './home/MomentsBlock.vue'
import NowNote from './home/NowNote.vue'
import NoticeBar from './home/NoticeBar.vue'
import PostsBlock from './home/PostsBlock.vue'
import ShelfBlock from './home/ShelfBlock.vue'

const props = defineProps<{ state: Extract<PageState, { kind: 'home' }> }>()
const blocks = computed(() => props.state.data.blocks)
type Of<T extends HomeBlock['type']> = Extract<HomeBlock, { type: T }>
const now = computed(() => (blocks.value.find((b) => b.type === 'now') as Of<'now'> | undefined) ?? null)
const hasAbout = computed(() => blocks.value.some((b) => b.type === 'about'))
</script>

<template>
  <div class="home">
    <template v-for="b in blocks" :key="b.type">
      <HeroBlock v-if="b.type === 'hero'" :config="b.config" />
      <NoticeBar v-else-if="b.type === 'notice'" :text="b.config.text" />
      <PostsBlock v-else-if="b.type === 'featured'" id="featured" :title="b.config.title" :posts="b.data.posts" layout="grid" />
      <PostsBlock v-else-if="b.type === 'latest_posts'" id="posts" :title="b.config.title" :intro="b.config.intro" :posts="b.data.posts" :layout="b.config.layout" />
      <MomentsBlock v-else-if="b.type === 'latest_moments'" id="moments" :title="b.config.title" :intro="b.config.intro" :moments="b.data.moments" />
      <ShelfBlock v-else-if="b.type === 'shelf'" id="shelf" :title="b.config.title" :intro="b.config.intro" :categories="b.data.categories" :tags="b.data.tags" />
      <AboutBlock v-else-if="b.type === 'about'" id="about" :title="b.config.title" :intro="b.config.intro" :text="b.config.text" :author="b.data.author" :now="now ? now.config : null" />
      <section v-else-if="b.type === 'now' && !hasAbout" class="section">
        <div class="wrap"><NowNote :title="b.config.title" :items="b.config.items" /></div>
      </section>
    </template>
  </div>
</template>
