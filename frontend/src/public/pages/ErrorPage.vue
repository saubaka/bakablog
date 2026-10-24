<script setup lang="ts">
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import { site, type PageState } from '../state'

defineProps<{ state: Extract<PageState, { kind: '500' }> }>()
const reload = (): void => location.reload()
</script>

<template>
  <div class="wrap">
    <section class="lost">
      <FxText tag="h1" :text="site.texts.error_title || '服务器打了个盹'" :intro="1" />
      <p v-fx="{ type: 'fade', intro: 2 }">{{ state.data.message || site.texts.error_text }}</p>
      <div class="hero__actions lost__actions" v-fx="{ type: 'fade', intro: 3 }">
        <button class="btn btn--fill" type="button" @click="reload"><Icon name="arrow-u" />重新加载</button>
        <NavLink class="btn" to="/">回首页</NavLink>
      </div>
    </section>
  </div>
</template>
