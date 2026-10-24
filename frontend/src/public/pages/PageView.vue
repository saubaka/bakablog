<script setup lang="ts">
/* A standalone page (about, links ...). Templates: plain (reading width), wide, sidebar (with a table of contents). */
import { computed } from 'vue'
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import ProseView from '../components/ProseView.vue'
import Toc from '../components/Toc.vue'
import { long } from '../fmt'
import type { PageState } from '../state'

const props = defineProps<{ state: Extract<PageState, { kind: 'page' }> }>()
const page = computed(() => props.state.data)
</script>

<template>
  <article class="wrap page" :class="[`page--${page.template}`, { 'wrap--read': page.template === 'plain' }]">
    <div :class="{ 'post-layout': page.template === 'sidebar' }">
      <header class="page-head" :class="{ 'post-head': page.template === 'sidebar' }">
        <FxText tag="h1" :text="page.title" :intro="0" />
        <p v-if="page.updated_at" class="meta" v-fx="{ type: 'fade', intro: 1 }">最后更新 {{ long(page.updated_at) }}</p>
      </header>
      <div :class="{ 'post-main': page.template === 'sidebar' }">
        <ProseView :html="page.html" />
      </div>
      <Toc v-if="page.template === 'sidebar'" :entries="page.toc" />
    </div>
  </article>
</template>
