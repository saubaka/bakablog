<script setup lang="ts">
import { computed } from 'vue'
import { vFx } from '@/fx/directive'
import NavLink from '@/ui/components/NavLink.vue'
import type { CategoryCount, TagCount } from '@/shared/types'
import { hash } from '@/shared/cover'
import SectionSplit from './SectionSplit.vue'

const props = defineProps<{ title: string; intro?: string; categories: CategoryCount[]; tags: TagCount[]; id?: string }>()
const shown = computed(() => props.categories.filter((c) => c.show_on_shelf))
const total = computed(() => props.categories.reduce((n, c) => n + c.count, 0))
/** A little variety for the tag cloud: three sizes from the server, a slight tilt from the name so it never changes between visits. */
const tilt = (t: TagCount): string => ((t.size ?? 1) >= 2 ? `r${(hash(t.name) % 3) + 1}` : '')
const tone = (t: TagCount): string => (t.color === 'sky' || t.color === 'rose' || t.color === 'mist' ? `tag--${t.color}` : '')
</script>

<template>
  <SectionSplit :id="id" :title="title" :intro="intro">
    <div v-fx="'rise'">
      <nav class="tabs" aria-label="分类">
        <NavLink class="tab" to="/blog">全部<span class="n">{{ total }}</span></NavLink>
        <NavLink v-for="c in shown" :key="c.id" class="tab" :to="c.url">{{ c.name }}<span class="n">{{ c.count }}</span></NavLink>
      </nav>
      <div v-if="tags.length" class="shelf-panel">
        <p>最常用的标签：</p>
        <div class="cloud" data-fx-stagger>
          <NavLink v-for="t in tags" :key="t.id" v-fx="'pop'" class="tag" :class="[tone(t), (t.size ?? 1) >= 2 ? `l${Math.min(t.size ?? 1, 3)}` : '', tilt(t)]" :to="t.url">{{ t.name }}</NavLink>
        </div>
      </div>
    </div>
  </SectionSplit>
</template>
