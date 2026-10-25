<script setup lang="ts">
/* The public page's frame (side menu, home, footer, bottom bar) around whatever the admin sends: a live look at unsaved settings. */
import Sprite from '@/ui/components/Sprite.vue'
import SiteFooter from '@/public/layout/SiteFooter.vue'
import TabBar from '@/public/layout/TabBar.vue'
import ThreadNav from '@/public/layout/ThreadNav.vue'
import Home from '@/public/pages/Home.vue'
import { page, site } from '@/public/state'
</script>

<template>
  <Sprite />
  <ThreadNav :items="site.nav.top" variant="side" label="主导航" />
  <main id="main">
    <Home v-if="page && page.kind === 'home'" :state="page" />
  </main>
  <SiteFooter />
  <TabBar />
</template>
