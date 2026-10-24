<script setup lang="ts">
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import MiniCard from '../components/MiniCard.vue'
import { site, type PageState } from '../state'
import { openSearch } from '../ui'

defineProps<{ state: Extract<PageState, { kind: '404' }> }>()
</script>

<template>
  <div class="wrap">
    <section class="lost">
      <span class="lost__code" v-fx="{ type: 'fade', intro: 1 }">404</span>
      <FxText tag="h1" :text="site.texts.not_found_title" :intro="2" />
      <p v-fx="{ type: 'fade', intro: 3 }">{{ site.texts.not_found_text }}</p>
      <div class="hero__actions lost__actions" v-fx="{ type: 'fade', intro: 4 }">
        <NavLink class="btn btn--fill" to="/"><Icon name="home" />回首页</NavLink>
        <NavLink class="btn" to="/blog">看看博客</NavLink>
        <button class="btn btn--ghost" type="button" @click="openSearch"><Icon name="search" />搜一搜</button>
      </div>
    </section>
    <section v-if="state.data.recent.length" class="stack lost__more">
      <h2 v-fx="'fade'">也许你想看这些</h2>
      <div class="related" data-fx-stagger>
        <MiniCard v-for="p in state.data.recent" :key="p.id" v-fx="'rise'" :post="p" />
      </div>
    </section>
  </div>
</template>
