<script setup lang="ts">
/* Phones and small tablets: the thread in the bar along the bottom edge, and the "more" drawer behind its last bead. */
import { computed } from 'vue'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import { iconFor } from '../nav'
import { ICONS } from '../icons'
import { site } from '../state'
import { closeMore, moreOpen } from '../ui'
import BottomSheet from './BottomSheet.vue'
import MotionSwitch from './MotionSwitch.vue'
import ThreadNav from './ThreadNav.vue'

/** The drawer lists what the bar has no room for: top-navigation and footer entries whose address is not already in the bar. */
const more = computed(() => {
  const inBar = new Set(site.value.nav.mobile.filter((i) => i.kind !== 'action').map((i) => i.url))
  const seen = new Set<string>()
  return [...site.value.nav.top, ...site.value.nav.footer].filter((i) => {
    if (i.kind === 'action' || inBar.has(i.url) || seen.has(i.url)) return false
    seen.add(i.url)
    return true
  })
})
</script>

<template>
  <ThreadNav :items="site.nav.mobile" variant="bottom" label="底部导航" />
  <BottomSheet :open="moreOpen" label="更多" @close="closeMore">
    <h2 class="sheet__title">更多</h2>
    <ul class="sheet-list">
      <li v-for="item in more" :key="item.url + item.label">
        <NavLink :to="item.url" :external="item.external"><Icon :name="iconFor(item, ICONS)" /><strong>{{ item.label }}</strong></NavLink>
      </li>
    </ul>
    <MotionSwitch />
  </BottomSheet>
</template>
