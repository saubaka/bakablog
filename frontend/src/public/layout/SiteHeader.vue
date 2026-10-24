<script setup lang="ts">
import Icon from '@/ui/components/Icon'
import { site } from '../state'
import { openSearch } from '../ui'
import ThreadNav from './ThreadNav.vue'
</script>

<template>
  <header class="site-header">
    <div class="wrap site-header__in">
      <RouterLink class="brand" to="/" :aria-label="`${site.name} · ${site.name_en}，回到首页`">
        <img v-if="site.logo" class="brand__logo" :src="site.logo.src" :alt="''" width="52" height="40">
        <span class="brand__text"><b>{{ site.name }}</b><small>{{ site.name_en }}</small></span>
      </RouterLink>
      <ThreadNav :items="site.nav.top" variant="side" label="主导航" />
      <div class="site-header__tools">
        <button v-if="site.features.search" class="icon-btn" type="button" aria-label="搜索（快捷键 /）" @click="openSearch"><Icon name="search" /></button>
        <a v-if="site.features.rss" class="icon-btn hide-sm" href="/feed/posts.xml" aria-label="订阅 RSS"><Icon name="rss" /></a>
      </div>
    </div>
  </header>
</template>
