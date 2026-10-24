<script setup lang="ts">
import { computed } from 'vue'
import { vFx } from '@/fx/directive'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import type { PostCard } from '@/shared/types'
import { planGrid } from '../../cards'
import PostCardView from '../../components/PostCardView.vue'
import PostRow from '../../components/PostRow.vue'
import { useViewport } from '../../viewport'
import SectionSplit from './SectionSplit.vue'

const props = defineProps<{ title: string; intro?: string; posts: PostCard[]; layout: 'mixed' | 'list' | 'grid'; id?: string }>()
const { cols } = useViewport()
const plan = computed(() => (props.layout === 'list' ? [] : planGrid(props.posts, props.layout, cols.value)))
</script>

<template>
  <SectionSplit :id="id" :title="title" :intro="intro">
    <template #label><NavLink class="text-link" to="/blog" v-fx="'fade'">全部文章<Icon name="arrow-r" /></NavLink></template>
    <div v-if="layout === 'list'" class="stack">
      <PostRow v-for="p in posts" :key="p.id" v-fx="'fade'" :post="p" />
    </div>
    <div v-else class="grid-6" data-fx-stagger>
      <PostCardView v-for="(p, i) in posts" :key="p.id" v-fx="'rise'" :class="`span-${plan[i]?.span ?? 3}`" :post="p" :layout="plan[i]?.layout ?? 'cover'" :level="3" />
    </div>
  </SectionSplit>
</template>
