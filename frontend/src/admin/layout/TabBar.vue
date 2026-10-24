<script setup lang="ts">
/* Phone: the bottom bar with the places used most, and "more" opening the whole menu as a drawer. */
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import AIcon from '../ui/AIcon'
import Drawer from '../ui/Drawer.vue'
import { entryFor, NAV, TABBAR } from '../nav'
import { openPalette } from './palette'

const route = useRoute()
const more = ref(false)
const current = (to: string): boolean => entryFor(route.path)?.to === to
</script>

<template>
  <nav class="adm-tabbar" aria-label="底部导航">
    <RouterLink v-for="t in TABBAR" :key="t.to" :to="t.to" :aria-current="current(t.to) ? 'page' : undefined"><AIcon :name="t.icon" />{{ t.label }}</RouterLink>
    <button type="button" aria-haspopup="dialog" @click="more = true"><AIcon name="more" />更多</button>
  </nav>
  <Drawer :open="more" title="全部页面" @close="more = false">
    <button class="btn btn--ghost adm-more__search" type="button" @click="more = false; openPalette()"><AIcon name="search" />搜索或跳转</button>
    <section v-for="g in NAV" :key="g.id" class="adm-more__group" @click="(e) => (e.target as HTMLElement).closest('a') && (more = false)">
      <h3>{{ g.label }}</h3>
      <ul><li v-for="it in g.items" :key="it.to"><RouterLink :to="it.to" :aria-current="current(it.to) ? 'page' : undefined"><AIcon :name="it.icon" />{{ it.label }}</RouterLink></li></ul>
    </section>
  </Drawer>
</template>
