<script setup lang="ts">
import { computed } from 'vue'
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import Phrase from '@/fx/Phrase'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import EmptyState from '../components/EmptyState.vue'
import Stamp from '../components/Stamp.vue'
import type { PageState } from '../state'

const props = defineProps<{ state: Extract<PageState, { kind: 'archive' }> }>()
const years = computed(() => props.state.data.years)
const total = computed(() => props.state.data.total)
</script>

<template>
  <div class="wrap">
    <header class="page-head">
      <span class="kicker" v-fx="{ type: 'pop', intro: 0 }"><Icon name="calendar" />归档</span>
      <FxText tag="h1" text="所有的文章" :intro="1" />
      <p v-fx="{ type: 'fade', intro: 2 }">一共 {{ total }} 篇。按时间从近到远，翻翻看有没有你漏掉的。</p>
    </header>
    <div v-if="years.length" class="archive">
      <section v-for="y in years" :key="y.year" class="archive__year" :aria-label="`${y.year} 年`">
        <h2><span class="archive__no" v-fx="'fade'">{{ y.year }}</span><small v-fx="'fade'">{{ y.count }} 篇</small></h2>
        <div class="archive__list">
          <div class="archive__spine" v-fx="'spine'" aria-hidden="true" />
          <div v-for="m in y.months" :key="m.month" class="archive__month">
            <h3 v-fx="'fade'">{{ m.month }} 月</h3>
            <NavLink v-for="p in m.posts" :key="p.id" v-fx="'fade'" class="archive__item" :to="p.url">
              <Stamp :iso="p.published_at" small />
              <strong><Phrase :text="p.title" /></strong>
              <span v-if="p.tags.length" class="tags"><span class="tag tag--sky">{{ p.tags[0]?.name }}</span></span>
            </NavLink>
          </div>
        </div>
      </section>
    </div>
    <EmptyState v-else title="还没有文章" text="等我写一篇就来。" />
  </div>
</template>
